using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

public sealed class CapabilityDataTests
{
    [Theory]
    [InlineData("data_query", """{"dataset":"employee_eligibility","client_id":42}""", "empty_query", null)]
    [InlineData("data_distinct_values", """{"dataset":"employee_eligibility","client_id":42,"column":"unknown"}""", "unknown_column", "column")]
    [InlineData("data_distinct_values", """{"dataset":"employee_eligibility","client_id":42,"column":"employee_id"}""", "blocked_column", "column")]
    [InlineData("data_distinct_values", """{"dataset":"employee_eligibility","client_id":42,"column":"record_token"}""", "column_not_listable", "column")]
    public async Task Invalid_questions_are_classified_before_person_lane_checks_without_querying(
        string tool, string arguments, string code, string? field)
    {
        using var harness = new CapabilityHarness();
        using var scope = harness.Principals.Push(new ApiPrincipal(Oid: "service", PrincipalType: "agent",
            ActingFor: new ActingUser("reader", Channel: "cowork")));
        var error = await Assert.ThrowsAsync<CapabilityException>(() =>
            harness.Service.InvokeAsync(tool, JsonNode.Parse(arguments)!.AsObject()));
        Assert.Equal(422, error.StatusCode);
        Assert.Equal(code, error.Code);
        Assert.Equal(field, error.Body()["error"]!["field"]?.GetValue<string>());
        Assert.Empty(harness.Queries);
    }

    [Fact]
    public async Task Numeric_filters_reach_the_warehouse_as_provider_supported_exact_scalars()
    {
        using var harness = new CapabilityHarness();
        harness.QueryResult = new(["worksite_id"],
            [new Dictionary<string, object?> { ["worksite_id"] = "UNIT-A" }], false, false);
        await harness.Service.InvokeAsync("data_query", JsonNode.Parse("""
            {"client_id":42.0,"dataset":"unit_year_master","tax_years":[2025.0],
             "select":["worksite_id"],"limit":25.0,
             "filters":[{"column":"annual_credit_usd","op":"gte","value":12345.67}]}
            """)!.AsObject());
        var spec = Assert.Single(harness.Queries);
        Assert.Equal(12345.67m, Assert.IsType<decimal>(Assert.Single(spec.Filters).Value));
        Assert.Equal(25, spec.Limit);
    }

    [Fact]
    public async Task Query_arguments_are_typed_and_forwarded_only_to_the_governed_port()
    {
        using var harness = new CapabilityHarness();
        var response = await harness.Service.InvokeAsync("data_query", JsonNode.Parse("""
            {"client_id":42,"dataset":"unit_year_master","tax_years":{"from":2024,"to":2025},
             "select":["worksite_id"],"measures":[{"column":"*","agg":"count","as":"row_count"}],
             "filters":[{"column":"worksite_id","op":"eq","value":"literal'; DROP TABLE ignored"}],
             "order_by":[{"column":"row_count","direction":"desc"}],"limit":25}
            """)!.AsObject());
        var spec = Assert.Single(harness.Queries);
        Assert.Equal(42, spec.ClientId);
        Assert.Equal(new[] { 2024, 2025 }, spec.TaxYears);
        Assert.Equal("worksite_id", Assert.Single(spec.GroupBy));
        Assert.Equal("literal'; DROP TABLE ignored", Assert.Single(spec.Filters).Value);
        Assert.Equal(25, spec.Limit);
        Assert.False(response.ContainsKey("user_only_facts"));
        Assert.Equal(8, response["facts"]!["rows"]![0]!["row_count"]!.GetValue<int>());
    }

    [Fact]
    public async Task Catalogue_uses_port_availability_and_never_advertises_blocked_columns()
    {
        using var harness = new CapabilityHarness();
        var response = await harness.Service.InvokeAsync("data_catalog", []);
        Assert.Equal(2, response["facts"]!["dataset_count"]!.GetValue<int>());
        Assert.Contains("9 dataset(s)", response["facts"]!["notes"]!.ToJsonString());
        var detail = await harness.Service.InvokeAsync("data_catalog", new JsonObject { ["dataset"] = "employee_eligibility" });
        Assert.DoesNotContain("employee_id", detail["facts"]!["datasets"]![0]!["columns"]!.ToJsonString());
        Assert.Empty(harness.Queries);
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData("cowork", false)]
    [InlineData("unknown", false)]
    [InlineData("teams", true)]
    [InlineData("m365-copilot", true)]
    public async Task Raw_employee_rows_have_an_explicit_person_lane_and_fail_closed_for_model_readers(string? channel, bool allowed)
    {
        using var harness = new CapabilityHarness();
        using var scope = harness.Principals.Push(new ApiPrincipal(Oid: "service", PrincipalType: "agent",
            ActingFor: new ActingUser("reader", Channel: channel)));
        harness.QueryResult = new GoldQueryResult(["record_token"],
            [new Dictionary<string, object?> { ["record_token"] = "opaque-synthetic-record" }], false, true);
        var args = new JsonObject { ["dataset"] = "employee_eligibility", ["client_id"] = 42, ["select"] = new JsonArray("record_token") };
        if (!allowed)
        {
            var error = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("data_query", args));
            Assert.Equal("employee_level_not_allowed", error.Code);
            Assert.Empty(harness.Queries);
            return;
        }
        var result = await harness.Service.InvokeAsync("data_query", args);
        Assert.Equal("rows", Assert.Single(result["user_only_facts"]!.AsArray())!.GetValue<string>());
        Assert.Equal("user", result["blocks"]![1]!["audience"]!.GetValue<string>());
        var envelope = new CapabilityResult("test", result["facts"]!.AsObject()) { UserOnlyFacts = ["rows"] };
        Assert.False(envelope.ModelFacts().ContainsKey("rows"));
    }

    [Fact]
    public async Task Aggregate_groups_count_distinct_people_not_pay_periods_and_remove_the_hidden_count()
    {
        using var harness = new CapabilityHarness();
        harness.QueryResult = new GoldQueryResult(["worksite_id", "row_count", "_capability_group_size"],
        [
            new Dictionary<string, object?> { ["worksite_id"] = "small", ["row_count"] = 52L, ["_capability_group_size"] = 1L },
            new Dictionary<string, object?> { ["worksite_id"] = "large", ["row_count"] = 104L, ["_capability_group_size"] = 6L },
        ], false, false);
        var result = await harness.Service.InvokeAsync("data_query", JsonNode.Parse("""
            {"dataset":"employee_eligibility","client_id":42,"tax_years":[2025],
             "select":["worksite_id"],"measures":[{"column":"*","agg":"count","as":"row_count"}]}
            """)!.AsObject());
        Assert.Equal("record_token", harness.Queries[0].Measures[^1].Column);
        Assert.Equal("count_distinct", harness.Queries[0].Measures[^1].Aggregation);
        Assert.Single(result["facts"]!["rows"]!.AsArray());
        Assert.Equal(1, result["facts"]!["small_groups"]!["suppressed_groups"]!.GetValue<int>());
        Assert.DoesNotContain("_capability_group_size", result.ToJsonString());
        Assert.DoesNotContain("\"small\"", result["facts"]!["rows"]!.ToJsonString());
    }

    [Fact]
    public async Task Cross_year_tokens_cannot_masquerade_as_distinct_people_without_the_missing_W1_binding()
    {
        using var harness = new CapabilityHarness();
        var error = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("data_query", JsonNode.Parse("""
            {"dataset":"employee_eligibility","client_id":42,"tax_years":[2024,2025],
             "measures":[{"column":"*","agg":"count","as":"row_count"}]}
            """)!.AsObject()));
        Assert.Equal(503, error.StatusCode);
        Assert.Contains("distinct-person", error.Body().ToJsonString());
        Assert.Empty(harness.Queries);
    }

    [Fact]
    public async Task Invalid_ranges_and_unentitled_clients_never_reach_the_query_port()
    {
        using var harness = new CapabilityHarness();
        var badRange = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("data_query", JsonNode.Parse("""
            {"dataset":"unit_year_master","client_id":42,"tax_years":{"from":1900,"to":2100},"select":["worksite_id"]}
            """)!.AsObject()));
        Assert.Equal(422, badRange.StatusCode);
        var denied = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("data_query",
            new JsonObject { ["dataset"] = "unit_year_master", ["client_id"] = 999, ["select"] = new JsonArray("worksite_id") }));
        Assert.Equal(403, denied.StatusCode);
        Assert.Empty(harness.Queries);
    }
}
