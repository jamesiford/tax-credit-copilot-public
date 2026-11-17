using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Tests.Composition;

public sealed class GuardedReplyTests
{
    [Fact]
    public void Clean_narration_precedes_independently_validated_blocks_and_trusted_footer()
    {
        var run = CompositionFixture.Credit();
        var result = GuardedReplyComposer.ComposeReply("Credit for 2023?", [run],
            "The credit is " + CompositionFixture.Placeholder("credit.annual_credit_usd") + ".");
        Assert.True(result.NarrationUsed);
        Assert.True(result.BlocksVerified);
        Assert.True(result.Guard.Passed);
        Assert.StartsWith("The credit is $3,640.50.", result.Text, StringComparison.Ordinal);
        Assert.Contains("### Min-Max method\n\n### Georgia Jobs Tax Credit", result.Text, StringComparison.Ordinal);
        Assert.EndsWith(CapabilityResult.Disclaimer, result.Body, StringComparison.Ordinal);
        Assert.EndsWith("trail abcdef012345_", result.Text, StringComparison.Ordinal);
        Assert.DoesNotContain("synthetic-run-42", result.Body, StringComparison.Ordinal);
        var index = FactIndex.FromFacts(JsonSerializer.SerializeToElement(GuardedReplyComposer.FactsOf([run])));
        Assert.True(NumericGuard.Check(result.Body, index).Passed);
    }

    [Theory]
    [InlineData("The credit is $3,640.50.")]
    [InlineData("The credit is $3,640.51.")]
    [InlineData("The headcount is 14.7.")]
    [InlineData("The credit is $3.64K.")]
    [InlineData("The credit is ３６４０.")]
    [InlineData("The credit is ٣٦٤٠.")]
    [InlineData("The credit is 3\u2009640.")]
    [InlineData("The credit is ½.")]
    [InlineData("The ratio is 12.5%.")]
    [InlineData("The opening date is 2023-07-29.")]
    [InlineData("The year is TY2024.")]
    [InlineData("An unbound value: {{facts.credit_min_max.nothing}}.")]
    [InlineData("A wrong format: {{facts.credit_min_max.credit.annual_credit_usd|Money}}.")]
    public void Any_untrusted_figure_or_placeholder_drops_the_entire_narration(string narration)
    {
        var run = CompositionFixture.Credit();
        var baseline = GuardedReplyComposer.ComposeReply("", [run], null);
        var rejected = GuardedReplyComposer.ComposeReply("", [run], narration);
        Assert.False(rejected.NarrationUsed);
        Assert.True(rejected.BlocksVerified);
        Assert.Equal("rejected", rejected.Guard.Status);
        Assert.Equal(baseline.Text, rejected.Text);
        var audit = JsonSerializer.Serialize(rejected.Guard);
        Assert.DoesNotContain(narration, audit, StringComparison.Ordinal);
        Assert.All(rejected.Guard.Violations, item => Assert.Null(item.NearestFact));
    }

    [Theory]
    [InlineData("about")]
    [InlineData("roughly")]
    [InlineData("approximately")]
    [InlineData("up to")]
    [InlineData("close to")]
    [InlineData("just over")]
    [InlineData("more or less")]
    [InlineData("~")]
    public void A_hedge_next_to_an_exact_placeholder_is_not_numerically_honest(string hedge)
    {
        var result = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit()],
            "The credit is " + hedge + " " + CompositionFixture.Placeholder("credit.annual_credit_usd"));
        Assert.False(result.NarrationUsed);
        Assert.Contains("narration_approximation", result.AuditRules);
    }

    [Theory]
    [InlineData("Rounded to the nearest thousand, the table is below.")]
    [InlineData("Rounding is not applied.")]
    [InlineData("The figures are approximately what you expect.")]
    public void Rounding_claims_are_refused_even_without_a_nearby_figure(string narration)
    {
        var reply = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit()], narration);
        Assert.False(reply.NarrationUsed);
        Assert.Contains("narration_approximation", reply.AuditRules);
    }

    [Fact]
    public void Reader_numbers_and_resolved_scope_are_allowed_but_person_rows_are_not_context()
    {
        var reply = GuardedReplyComposer.ComposeReply("What if we hire 5 people?", [CompositionFixture.Credit()],
            "With 5 hires in TY2023 for client 2001, see the table.");
        Assert.True(reply.NarrationUsed);
        Assert.False(GuardedReplyComposer.ComposeReply("", [CompositionFixture.Employee()],
            "The wage is 613.47.").NarrationUsed);
    }

    [Theory]
    [InlineData("See https://untrusted.example/statute", "output_policy_url")]
    [InlineData("See www.untrusted.example/statute", "output_policy_url")]
    [InlineData("See [the source](//untrusted.example/statute)", "output_policy_url")]
    [InlineData("See [the source](javascript:alert())", "output_policy_url")]
    [InlineData("See [the source](rules)", "output_policy_url")]
    [InlineData("Ask review@example.invalid", "output_policy_email")]
    [InlineData("```\nA table\n```", "output_policy_code_fence")]
    [InlineData("As your tax attorney, this is formal tax advice.", "output_policy_legal_advice")]
    [InlineData("You should file.", "output_policy_legal_advice")]
    [InlineData("You are protected from an audit.", "output_policy_legal_advice")]
    public void Output_policy_is_not_replaced_by_a_numeric_check(string narration, string code)
    {
        var reply = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit()], narration);
        Assert.False(reply.NarrationUsed);
        Assert.Contains(code, reply.AuditRules);
    }

    [Theory]
    [InlineData("https://docs.example.invalid/rules", true)]
    [InlineData("https://sub.docs.example.invalid/rules", true)]
    [InlineData("https://docs.example.invalid.attacker.invalid/rules", false)]
    [InlineData("https://docs.example.invalid@attacker.invalid/rules", false)]
    public void Explicit_link_allow_list_compares_hosts_not_substrings(string url, bool accepted)
    {
        var reply = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit()], "See " + url,
            ["docs.example.invalid"]);
        Assert.Equal(accepted, reply.NarrationUsed);
    }

    [Fact]
    public void Unverified_blocks_are_withheld_even_if_narration_is_clean()
    {
        var run = CompositionFixture.Credit();
        run = run with { Result = run.Result with { Blocks = [CapabilityResult.Block("paragraph", "Credit $9,999")] } };
        var reply = GuardedReplyComposer.ComposeReply("", [run], "The platform has the answer.");
        Assert.False(reply.BlocksVerified);
        Assert.False(reply.NarrationUsed);
        Assert.NotNull(reply.Notice);
        Assert.DoesNotContain("9,999", reply.Text, StringComparison.Ordinal);
        Assert.Contains(GuardedReplyComposer.VerificationNotice, reply.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Narrator_percent_format_does_not_grant_authority_to_invalid_blocks()
    {
        var run = CompositionFixture.Credit();
        run = run with { Result = run.Result with { Blocks = [CapabilityResult.Block("paragraph", "Share 12.5%")] } };
        var reply = GuardedReplyComposer.ComposeReply("", [run],
            CompositionFixture.Placeholder("population.ratio", "percent"));
        Assert.False(reply.BlocksVerified);
        Assert.DoesNotContain("12.5%", reply.Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("unknown")]
    [InlineData("ragged")]
    [InlineData("bullets")]
    public void Malformed_producer_blocks_fail_closed_without_echoing_input(string kind)
    {
        var block = kind switch
        {
            "ragged" => JsonNode.Parse("""{"kind":"table","rows":[["A"],["B","C"]]}"""),
            "bullets" => JsonNode.Parse("""{"kind":"bullets","rows":[["A","B"]]}"""),
            _ => JsonNode.Parse("""{"kind":"unexpected","text":"producer's private exception"}"""),
        };
        var run = CompositionFixture.Credit();
        run = run with { Result = run.Result with { Blocks = [block] } };
        var reply = GuardedReplyComposer.ComposeReply("", [run], null);
        Assert.False(reply.BlocksVerified);
        Assert.DoesNotContain("private exception", reply.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Composition_is_cached_and_invalidated_only_for_new_narration_or_fallback()
    {
        var run = CompositionFixture.Credit();
        var plan = new CompositionPlan("", [run]);
        plan.Narrate("The platform has the answer.");
        var first = plan.ComposedFor();
        Assert.Same(first, plan.ComposedFor());
        run.Result.Facts.Clear();
        Assert.Same(first, plan.ComposedFor());
        plan.Narrate("The credit is " + CompositionFixture.Placeholder("credit.annual_credit_usd"));
        var second = plan.ComposedFor();
        Assert.NotSame(first, second);
        Assert.True(second.NarrationUsed);
        plan.FallBack();
        Assert.True(plan.Degraded);
        Assert.Null(plan.Narration);
        Assert.False(plan.ComposedFor().NarrationUsed);
    }

    [Fact]
    public void Full_finished_output_is_checked_independently_of_each_valid_placeholder()
    {
        var run = new CompositionRun("synthetic_credit", [], new CapabilityResult("synthetic_credit",
            new JsonObject { ["left"] = 12, ["right"] = 34 }), "q");
        var reply = GuardedReplyComposer.ComposeReply("", [run],
            "{{facts.q.left|text}}{{facts.q.right|text}}");
        Assert.False(reply.NarrationUsed);
        Assert.Contains(reply.Guard.Violations, item => item.Stage == "final");
        Assert.DoesNotContain("1234", reply.Body, StringComparison.Ordinal);
    }

    [Fact]
    public void Empty_results_are_unavailable_not_an_invented_zero()
    {
        var reply = GuardedReplyComposer.ComposeReply("", [], null);
        Assert.Equal(CapabilityResult.Disclaimer, reply.Text);
        Assert.True(reply.Guard.Passed);
        Assert.False(reply.NarrationUsed);
        var rejected = GuardedReplyComposer.ComposeReply("", [], "The credit is 0.");
        Assert.Equal("rejected", rejected.Guard.Status);
        Assert.Equal(reply.Text, rejected.Text);
    }
}
