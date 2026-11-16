using System.Text.Json;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Tests.Composition;

public sealed class PlaceholderTests
{
    private static FactIndex Facts() => FactIndex.FromFacts(JsonSerializer.SerializeToElement(new
    {
        credit = new { annual_credit_usd = "3640.50", average_headcount = "14.73", qualifying_jobs = (int?)null },
        population = new { eligible = 51, ratio = "0.125" },
        snapshot = new { tax_year = 2023, begin = "2023-07-28" },
        citation = "Code 48-7-40.26",
        rows = new[] { new { month_01 = 11 } },
        flag = true,
    }));

    [Theory]
    [InlineData("{{facts.credit.annual_credit_usd}}", "$3,640.50")]
    [InlineData("{{ facts.credit.annual_credit_usd | money }}", "$3,640.50")]
    [InlineData("{{facts.credit.annual_credit_usd|compact_money}}", "$3.6405K")]
    [InlineData("{{facts.credit.annual_credit_usd|number}}", "3,640.5")]
    [InlineData("{{facts.credit.average_headcount}}", "14.73")]
    [InlineData("{{facts.population.eligible|count}}", "51")]
    [InlineData("{{facts.population.ratio|percent}}", "12.5%")]
    [InlineData("{{facts.snapshot.tax_year}}", "2023")]
    [InlineData("{{facts.snapshot.begin}}", "2023-07-28")]
    [InlineData("{{facts.citation}}", "Code 48-7-40.26")]
    public void Trusted_renderings_are_exact(string token, string expected)
    {
        var result = FactPlaceholders.Expand(token, Facts());
        Assert.Equal(expected, result.Text);
        Assert.Equal("█", result.Masked);
        Assert.True(NumericGuard.CheckRaw(result.Masked).Passed);
        Assert.True(NumericGuard.Check(result.Text, result.Index).Passed);
    }

    [Theory]
    [InlineData("{{facts.absent}}")]
    [InlineData("{{facts.credit}}")]
    [InlineData("{{facts.credit.annual_credit_usd|accounting}}")]
    [InlineData("{{facts.credit.annual_credit_usd|Money}}")]
    [InlineData("{{facts.credit.qualifying_jobs}}")]
    [InlineData("{{facts.flag}}")]
    [InlineData("{{facts.citation|money}}")]
    [InlineData("{{facts.credit.average_headcount|count}}")]
    [InlineData("{{facts.credit.annual_credit_usd|year}}")]
    [InlineData("{{facts.credit.annual_credit_usd|date}}")]
    [InlineData("{{facts.}}")]
    [InlineData("{{credit.annual_credit_usd}}")]
    [InlineData("{{facts.credit.annual_credit_usd}")]
    [InlineData("{{facts.credit.annual_credit_usd|money123}}")]
    [InlineData("```\n{{facts.population.eligible}}\n```")]
    [InlineData("~~~\n{{facts.population.eligible}}\n~~~")]
    public void Unsafe_placeholders_are_refused_with_only_a_rule_code(string narration)
    {
        var exception = Assert.Throws<PlaceholderException>(() => FactPlaceholders.Expand(narration, Facts()));
        Assert.DoesNotContain("facts.", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Known_digit_components_are_validated_before_the_caller_masks_them()
    {
        const string narration = "The count is {{facts.rows.0.month_01|count}}.";
        Assert.False(NumericGuard.CheckRaw(narration).Passed);
        var result = FactPlaceholders.Expand(narration, Facts());
        Assert.Equal("The count is █.", result.Masked);
        Assert.Equal("The count is 11.", result.Text);
        Assert.True(NumericGuard.CheckRaw(result.Masked).Passed);
    }

    [Fact]
    public void Percent_authority_attaches_only_to_an_explicitly_rendered_path()
    {
        var original = Facts();
        Assert.False(NumericGuard.Check("12.5%", original).Passed);
        var expanded = FactPlaceholders.Expand("{{facts.population.ratio|percent}}", original);
        Assert.True(NumericGuard.Check("12.5%", expanded.Index).Passed);
        Assert.False(NumericGuard.Check("12.5%", original).Passed);
    }

    [Fact]
    public void Conflicting_paths_are_not_maskable()
    {
        var first = JsonSerializer.SerializeToElement(new { x = 1 });
        var second = JsonSerializer.SerializeToElement(new { x = 2 });
        var facts = FactIndex.FromFacts([first, second]);
        Assert.Throws<PlaceholderException>(() => FactPlaceholders.Expand("{{facts.x}}", facts));
    }

    [Fact]
    public void A_closed_fence_does_not_capture_later_placeholders()
    {
        var expanded = FactPlaceholders.Expand("```\nexample\n```\nthen {{facts.population.eligible}}", Facts());
        Assert.EndsWith("then 51", expanded.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Unbounded_exponents_never_reach_the_shared_formatter()
    {
        using var document = JsonDocument.Parse("""{"amount":1e999999999}""");
        var facts = FactIndex.FromFacts(document.RootElement);
        var exception = Assert.Throws<PlaceholderException>(() => FactPlaceholders.Expand("{{facts.amount}}", facts));
        Assert.Equal("unrenderable_placeholder", exception.Message);
    }
}
