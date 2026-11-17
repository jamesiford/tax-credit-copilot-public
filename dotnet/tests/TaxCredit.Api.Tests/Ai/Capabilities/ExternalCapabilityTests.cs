using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

public sealed class ExternalCapabilityTests
{
    [Theory]
    [InlineData("client_eligibility")]
    [InlineData("client_at_risk")]
    [InlineData("simulate")]
    [InlineData("calc_walkthrough")]
    public async Task Required_sibling_contract_renders_exact_facts_and_carries_its_evidence(string tool)
    {
        using var harness = new CapabilityHarness();
        var facts = JsonNode.Parse(Facts(tool))!.AsObject();
        var provenance = CapabilityResult.Evidence("synthetic-run", "synthetic-pack", "synthetic-method", "synthetic-trail", "stored projection");
        harness.Read = (name, args) =>
        {
            Assert.Equal(tool, name);
            Assert.Equal(42, args["client_id"]!.GetValue<int>());
            return Task.FromResult(new CapabilityRead(facts.DeepClone().AsObject(), provenance));
        };
        var args = new JsonObject { ["client_id"] = 42, ["tax_year"] = 2025 };
        if (tool == "simulate") { args["worksite_id"] = "UNIT-A"; }
        var result = await harness.Service.InvokeAsync(tool, args);
        Assert.True(JsonNode.DeepEquals(facts, result["facts"]));
        Assert.True(JsonNode.DeepEquals(provenance, result["provenance"]));
        var rendered = string.Join("\n", result["blocks"]!.AsArray().SelectMany(block =>
            new[] { block!["text"]!.GetValue<string>() }.Concat(block["rows"]!.AsArray()
                .SelectMany(row => row!.AsArray().Select(cell => cell!.GetValue<string>())))));
        var check = NumericGuard.Check(rendered, JsonSerializer.SerializeToElement(facts));
        Assert.True(check.Passed, "A rendered numeral was not supplied by the sibling contract.");
    }

    private static string Facts(string tool) => tool switch
    {
        "client_eligibility" => """
            {"snapshot":{"calculated":true,"selected_tax_year":2025},
             "credit":{"credit_name":"Synthetic credit","average_headcount":"12.5",
               "prior_period_average_headcount":"9","qualifying_jobs":"3.5",
               "annual_credit_usd":"1250","lifetime_credit_usd":"2500",
               "benefit_period_years":2,"citation":"Example rule"}}
            """,
        "client_at_risk" => """
            {"calculated":true,"within_band":3,"eligible":8,"band_weekly_hours":5,
             "binding_floors":{"hours":2,"wages":1},"jobs_at_risk":"2.5",
             "method_note":"Completed year; not a prediction."}
            """,
        "simulate" => """
            {"scope":{"worksite_id":"UNIT-A","tax_year":2025},"detail":"A bounded simulation.",
             "baseline":{"average_headcount":"12.5","net_new_vs_base":"3.5","annual_credit_usd":"1250","series_credit_usd":"2500"},
             "projected":{"average_headcount":"13.5","net_new_vs_base":"4.5","annual_credit_usd":"1500","series_credit_usd":"3000"},
             "delta":{"average_headcount":"1","net_new_vs_base":"1","annual_credit_usd":"250","series_credit_usd":"500"}}
            """,
        "calc_walkthrough" => """
            {"title":"Stored calculation","citation":"Example rule","evidence_hash":"synthetic-trail",
             "steps":[{"step":"Price","inputs":{"jobs":"3.5","rate":"1250"},
               "formula":"jobs times rate","output":{"credit":"4375"},"citation":"Example rule"}]}
            """,
        _ => throw new ArgumentOutOfRangeException(nameof(tool))
    };
}
