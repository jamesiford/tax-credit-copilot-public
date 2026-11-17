using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Tests.Composition;

public sealed class ModelLaneTests
{
    [Fact]
    public void Every_model_request_projection_contains_names_and_structure_never_person_values()
    {
        var run = CompositionFixture.Employee();
        foreach (var fenced in new[] { false, true })
        {
            var brief = GuardedReplyComposer.NarrationBrief("Show people", [run], fenced);
            var answer = GuardedReplyComposer.ModelAnswer(run, brief);
            foreach (var payload in new[] { brief, answer, GuardedReplyComposer.ModelFactsOf([run]) })
            {
                var json = payload.ToJsonString();
                Assert.DoesNotContain("synthetic-record-", json, StringComparison.Ordinal);
                Assert.DoesNotContain("613.47", json, StringComparison.Ordinal);
                Assert.DoesNotContain("private-method", json, StringComparison.Ordinal);
                Assert.DoesNotContain("data_query.rows.", json, StringComparison.Ordinal);
            }
            Assert.Null(answer["result"]);
            Assert.Contains("data_query.row_count", answer.ToJsonString(), StringComparison.Ordinal);
            Assert.Empty(brief["notes"]!.AsArray());
        }
        var reply = GuardedReplyComposer.ComposeReply("Show people", [run], "Here are the people.");
        Assert.True(reply.NarrationUsed);
        Assert.Contains("synthetic-record-990001", reply.Text, StringComparison.Ordinal);
        Assert.Contains("613.47", reply.Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("{{facts.data_query.rows.0.total_wages}}")]
    [InlineData("{{facts.data_query.rows.0.record_token}}")]
    [InlineData("{{facts.data_query.rows.1.method}}")]
    [InlineData("The wage is 613.47.")]
    [InlineData("Copied synthetic-record-990001.")]
    [InlineData("Copied private-method.")]
    public void A_person_only_path_or_copied_row_is_rejected_without_private_audit_material(string narration)
    {
        var reply = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Employee()], narration);
        Assert.False(reply.NarrationUsed);
        Assert.Equal("rejected", reply.Guard.Status);
        Assert.Contains("synthetic-record-990001", reply.Text, StringComparison.Ordinal);
        var audit = JsonSerializer.Serialize(reply.Guard);
        Assert.DoesNotContain("rows", audit, StringComparison.Ordinal);
        Assert.DoesNotContain("total_wages", audit, StringComparison.Ordinal);
        Assert.DoesNotContain("613.47", audit, StringComparison.Ordinal);
        Assert.DoesNotContain("synthetic-record-", audit, StringComparison.Ordinal);
        Assert.DoesNotContain("private-method", audit, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("user")]
    [InlineData("future-audience")]
    [InlineData("")]
    [InlineData(null)]
    public void Unknown_fact_audience_hides_rows_even_when_producer_omits_user_only_keys(string? audience)
    {
        var run = CompositionFixture.Employee();
        run.Result.Facts["audience"] = audience;
        run = run with { Result = run.Result with { UserOnlyFacts = [] } };
        var model = GuardedReplyComposer.ModelFactsOf([run]);
        Assert.Null(model[run.Label]!["rows"]);
        Assert.DoesNotContain("synthetic-record-", GuardedReplyComposer.Brief("", [run]).ToJsonString(), StringComparison.Ordinal);
        Assert.Contains("synthetic-record-", GuardedReplyComposer.ComposeReply("", [run], null).Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("user")]
    [InlineData("future-audience")]
    [InlineData("")]
    [InlineData(null)]
    public void Unknown_block_audience_never_exposes_block_text_or_warnings_to_the_model(string? audience)
    {
        var run = CompositionFixture.Employee();
        run.Result.Blocks[1]!["audience"] = audience;
        var answer = GuardedReplyComposer.ModelAnswer(run, GuardedReplyComposer.Brief("", [run]));
        Assert.DoesNotContain("synthetic-record-", answer.ToJsonString(), StringComparison.Ordinal);
        Assert.Empty(answer["notes"]!.AsArray());
    }

    [Fact]
    public void Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised()
    {
        var rows = new JsonArray(Enumerable.Range(0, 60).Select(index => (JsonNode)new JsonObject
        {
            ["method"] = "method-" + index,
            ["n"] = index + 10,
        }).ToArray());
        var run = new CompositionRun("data_query", [], new CapabilityResult("data_query", new JsonObject
        {
            ["row_count"] = rows.Count,
            ["rows"] = rows,
        }), "q");
        var brief = GuardedReplyComposer.Brief("", [run]).ToJsonString();
        Assert.Contains("q.rows.49.n", brief, StringComparison.Ordinal);
        Assert.DoesNotContain("q.rows.50.n", brief, StringComparison.Ordinal);
        Assert.DoesNotContain("method-0", brief, StringComparison.Ordinal);
        Assert.True(GuardedReplyComposer.ComposeReply("", [run], "Count {{facts.q.rows.3.n}}.").NarrationUsed);
        var rejected = GuardedReplyComposer.ComposeReply("", [run], "Count {{facts.q.rows.51.n}}.");
        Assert.False(rejected.NarrationUsed);
        Assert.Contains("outside_model_view", rejected.AuditRules);
        Assert.Equal(60, GuardedReplyComposer.FactsOf([run])["q"]!["rows"]!.AsArray().Count);
    }

    [Fact]
    public void Every_brief_token_is_copyable_renderable_and_contains_no_value()
    {
        var run = CompositionFixture.Credit();
        var brief = GuardedReplyComposer.Brief("A question", [run], fenced: true);
        var json = brief.ToJsonString();
        Assert.DoesNotContain("3640.50", json, StringComparison.Ordinal);
        Assert.DoesNotContain("14.73", json, StringComparison.Ordinal);
        Assert.StartsWith("<<<UNTRUSTED source=reader question>>>", brief["question"]!.GetValue<string>(), StringComparison.Ordinal);
        foreach (var path in brief["fact_paths"]!.AsArray().OfType<JsonObject>())
        {
            Assert.NotNull(path["format"]);
            var reply = GuardedReplyComposer.ComposeReply("", [run], "The fact is " + path["placeholder"]!.GetValue<string>());
            Assert.True(reply.NarrationUsed, path.ToJsonString());
            Assert.DoesNotContain("{{", reply.Text, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void A_lookup_receives_only_its_declared_model_safe_structural_projection()
    {
        var run = new CompositionRun("data_catalog", [], new CapabilityResult("data_catalog", JsonNode.Parse("""
            {"datasets":[{"name":"unit_summary","columns":[{"name":"worksite_id"},{"name":"tax_year"}],"column_count":2}]}
            """)!.AsObject())
        {
            Blocks = [CapabilityResult.Block("heading", "Queryable data")],
        }, "data_catalog", IsLookup: true);
        var answer = GuardedReplyComposer.ModelAnswer(run, GuardedReplyComposer.Brief("", [run]));
        Assert.Contains("worksite_id", answer["result"]!.ToJsonString(), StringComparison.Ordinal);
        Assert.All(answer["fact_paths"]!.AsArray(), path => Assert.NotEqual("text", path!["format"]!.GetValue<string>()));
        var alone = GuardedReplyComposer.ComposeReply("", [run], null);
        Assert.Contains("Queryable data", alone.Text, StringComparison.Ordinal);
        var together = GuardedReplyComposer.ComposeReply("", [run, CompositionFixture.Credit()], null);
        Assert.DoesNotContain("Queryable data", together.Text, StringComparison.Ordinal);
        Assert.Contains("Annual credit", together.Text, StringComparison.Ordinal);
    }

    [Fact]
    public void Even_a_misdeclared_lookup_cannot_receive_an_employee_identifier()
    {
        var run = CompositionFixture.Employee() with { IsLookup = true };
        var answer = GuardedReplyComposer.ModelAnswer(run, GuardedReplyComposer.Brief("", [run]));
        Assert.DoesNotContain("synthetic-record-", answer.ToJsonString(), StringComparison.Ordinal);
        Assert.Null(answer["result"]!["rows"]);
    }

    [Fact]
    public void Confirmation_tokens_are_neither_placeholder_authority_nor_reader_or_model_content()
    {
        var run = CompositionFixture.Credit();
        run.Result.Facts["confirmation"] = new JsonObject { ["token"] = "synthetic-secret-token" };
        run.Result.Facts["copy"] = "synthetic-secret-token";
        var brief = GuardedReplyComposer.Brief("Ask", [run]);
        Assert.DoesNotContain("confirmation", brief.ToJsonString(), StringComparison.Ordinal);
        Assert.DoesNotContain("synthetic-secret-token", GuardedReplyComposer.FactsOf([run]).ToJsonString(), StringComparison.Ordinal);
        var reply = GuardedReplyComposer.ComposeReply("", [run], "Use synthetic-secret-token.");
        Assert.False(reply.NarrationUsed);
        Assert.DoesNotContain("synthetic-secret-token", JsonSerializer.Serialize(reply), StringComparison.Ordinal);
        run.Result.Blocks.Add(CapabilityResult.Block("paragraph", "Token synthetic-secret-token."));
        Assert.False(GuardedReplyComposer.ComposeReply("", [run], null).BlocksVerified);
    }

    [Fact]
    public void Multiple_methods_keep_independent_paths_and_headings()
    {
        var minMax = CompositionFixture.Credit();
        var payPeriod = CompositionFixture.Credit("credit_pay_period", "pay_period");
        payPeriod.Result.Facts["population"]!["min_max_eligible"] = 49;
        var text = GuardedReplyComposer.ComposeReply("", [minMax, payPeriod],
            "{{facts.credit_min_max.population.min_max_eligible}} versus {{facts.credit_pay_period.population.min_max_eligible}}.").Text;
        Assert.StartsWith("51 versus 49.", text, StringComparison.Ordinal);
        Assert.True(text.IndexOf("Min-Max method", StringComparison.Ordinal) < text.IndexOf("Pay Period method", StringComparison.Ordinal));
        Assert.Equal(1, text.Split("_Source:", StringSplitOptions.None).Length - 1);
    }

    [Fact]
    public void Duplicate_labels_do_not_silently_replace_a_result()
    {
        var result = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit(), CompositionFixture.Credit()], null);
        Assert.False(result.BlocksVerified);
        Assert.Equal("rejected", result.Guard.Status);
    }
}
