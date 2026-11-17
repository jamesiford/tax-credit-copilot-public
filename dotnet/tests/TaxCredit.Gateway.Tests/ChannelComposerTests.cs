using System.Text.Json;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Gateway.Execution;

namespace TaxCredit.Gateway.Tests;

public sealed class ChannelComposerTests
{
    private static FactIndex Facts() => FactIndex.FromFacts(JsonSerializer.SerializeToElement(new
    {
        credit = new { annual_credit_usd = "3500.00", average_headcount = 12.67, missing = (string?)null },
        years = new[] { new { tax_year = 2023, eligible = 539 } },
        ratio = 0.125,
        begin = "2023-07-28",
    }));

    [Theory]
    [InlineData("Credit: {{facts.credit.annual_credit_usd}}.", "Credit: $3,500.")]
    [InlineData("{{ facts.years.0.eligible | count }} qualify.", "539 qualify.")]
    [InlineData("The year is {{facts.years.0.tax_year|year}}.", "The year is 2023.")]
    [InlineData("{{facts.ratio|percent}}", "12.5%")]
    [InlineData("{{facts.begin}}", "2023-07-28")]
    public void Valid_paths_are_masked_before_raw_check_and_rendered_exactly(string narration, string expected)
    {
        var reply = ChannelComposer.Compose("539 eligible", narration, Facts());
        Assert.True(reply.NarrationUsed);
        Assert.True(reply.Guard.Passed);
        Assert.StartsWith(expected, reply.Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("The correct typed credit is $3,500.")]
    [InlineData("The wrong credit is $3,540.")]
    [InlineData("{{facts.credit.annual_credit_usd}} for 5 hires.")]
    [InlineData("{{facts.credit.unknown}}")]
    [InlineData("{{facts.credit.missing}}")]
    [InlineData("{{facts.credit}}")]
    [InlineData("{{facts.credit.annual_credit_usd|accounting}}")]
    [InlineData("{{facts.credit.average_headcount|count}}")]
    [InlineData("{{facts.credit.annual_credit_usd}")]
    [InlineData("{{credit.annual_credit_usd}}")]
    [InlineData("```\n{{facts.years.0.eligible}}\n```")]
    [InlineData("~~~\n{{facts.years.0.eligible}}\n~~~")]
    [InlineData("\uff13\uff15\uff10\uff10 dollars")]
    [InlineData("Unverified 2024-01-01")]
    [InlineData("Unverified 12.5%")]
    [InlineData("Unverified $3.54K")]
    public void A_rejected_narration_is_dropped_whole(string narration)
    {
        var reply = ChannelComposer.Compose("539 eligible", narration, Facts());
        Assert.False(reply.NarrationUsed);
        Assert.False(reply.Guard.Passed);
        Assert.True(reply.BlocksVerified);
        Assert.StartsWith("539 eligible\n\nNot tax advice:", reply.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Conflicting_paths_need_a_namespace_and_untrusted_blocks_are_withheld()
    {
        var facts = new[] { JsonSerializer.SerializeToElement(new { x = 1 }), JsonSerializer.SerializeToElement(new { x = 2 }) };
        var ambiguous = ChannelComposer.Compose("", "{{facts.x}}", FactIndex.FromFacts(facts));
        Assert.False(ambiguous.NarrationUsed);
        var named = ChannelComposer.Compose("", "{{facts.first.x}} and {{facts.second.x}}",
            FactIndex.FromFacts(facts, ["first", "second"]));
        Assert.True(named.NarrationUsed);
        var invalidBlock = ChannelComposer.Compose("$9,999", "A clean sentence.", Facts());
        Assert.False(invalidBlock.BlocksVerified);
        Assert.DoesNotContain("9,999", invalidBlock.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Reader_context_is_explicit_and_never_derived_from_model_words()
    {
        var rejected = ChannelComposer.Compose("", "With 5 hires.", Facts());
        Assert.False(rejected.NarrationUsed);
        var allowed = ChannelComposer.Compose("", "With 5 hires.", Facts(), AllowedContext.Build(["What if we hire 5 people?"]));
        Assert.True(allowed.NarrationUsed);
    }

    [Theory]
    [InlineData("Roughly {{facts.years.0.eligible}} qualify.")]
    [InlineData("{{facts.years.0.eligible}} or so qualify.")]
    [InlineData("Up to {{facts.years.0.eligible}} qualify.")]
    [InlineData("~{{facts.years.0.eligible}} qualify.")]
    [InlineData("These figures are not rounded.")]
    [InlineData("See https://example.test for details.")]
    [InlineData("Email analyst@example.test for details.")]
    [InlineData("As your tax advisor, this is formal tax advice.")]
    [InlineData("You should file a return.")]
    [InlineData("You are protected from an audit.")]
    [InlineData("```\nA sentence with no numbers.\n```")]
    public void Approximation_and_unsafe_words_are_rejected_without_repeating_the_prose(string narration)
    {
        var reply = ChannelComposer.Compose("539 eligible", narration, Facts());
        Assert.False(reply.NarrationUsed);
        Assert.False(reply.Guard.Passed);
        Assert.True(reply.BlocksVerified);
        Assert.DoesNotContain(narration, reply.Text, StringComparison.Ordinal);
        Assert.All(reply.Guard.Violations, violation =>
            Assert.DoesNotContain(narration, violation.Reason, StringComparison.Ordinal));
    }
}
