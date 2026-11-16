using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Ai.Capabilities;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using static TaxCredit.Api.Tests.Ai.CapabilityBindingsFixture;

namespace TaxCredit.Api.Tests.Ai;

public sealed class CapabilityBindingsReadTests
{
    [Theory]
    [InlineData("client_at_risk", """{"client_id":1001,"tax_year":2025}""")]
    [InlineData("client_discovery", """{"client_id":1001,"tax_year":2025,"state":"GA"}""")]
    [InlineData("simulate", """{"client_id":1001,"tax_year":2025,"worksite_id":"GA_ATL_HQ","magnitude":1}""")]
    [InlineData("calc_walkthrough", """{"client_id":1001,"tax_year":2025}""")]
    [InlineData("findings_list", """{"client_id":1001,"tax_year":2025}""")]
    [InlineData("program_catalog", """{}""")]
    [InlineData("program_catalog", """{"program_code":"GA_JTC"}""")]
    public async Task Ordinary_composition_dispatches_canonical_production_reads(string tool, string json)
    {
        await using var fixture = await Start();
        var result = await fixture.Invoke(tool, JsonNode.Parse(json)!.AsObject());
        var facts = result["facts"]!.AsObject();
        Assert.NotEmpty(facts);
        Assert.NotEmpty(result["blocks"]!.AsArray());
        if (tool == "client_discovery")
        {
            Assert.Contains("GA_JTC", facts["excluded"]!.AsArray().Select(value => value!.GetValue<string>()));
            Assert.DoesNotContain(facts["hits"]!.AsArray(), hit => hit!["credit_code"]!.GetValue<string>() == "GA_JTC");
        }
        if (tool == "calc_walkthrough")
        {
            Assert.NotEmpty(facts["steps"]!.AsArray());
            Assert.Equal(facts["evidence_hash"]!.GetValue<string>()[7..], result["provenance"]!["trail_sha256"]!.GetValue<string>());
        }
        if (tool == "client_at_risk")
        {
            Assert.True(facts["calculated"]!.GetValue<bool>());
            Assert.Contains("cohort", result["user_only_facts"]!.AsArray().Select(value => value!.GetValue<string>()));
        }
    }

    [Fact]
    public async Task Stored_employee_handle_dispatches_the_same_authorized_drill_as_the_page()
    {
        await using var fixture = await Start();
        using var scope = fixture.Host.App.Services.CreateScope();
        using var identity = scope.ServiceProvider.GetRequiredService<IApiPrincipalAccessor>().Push(Writer);
        var mediator = scope.ServiceProvider.GetRequiredService<IMediator>();
        var arguments = new ReadArguments(new Dictionary<string, string?> { ["account_id"] = "1001", ["tax_year"] = "2025", ["state"] = "GA", ["limit"] = "1" });
        var page = JsonSerializerNode(await mediator.Send(new StoredReadQuery("eligibility", arguments)));
        var token = page["rows"]![0]!["record_token"]!.GetValue<string>();
        var args = new JsonObject { ["client_id"] = 1001, ["tax_year"] = 2025, ["record_token"] = token };
        var result = await fixture.Invoke("employee_drill", args);
        Assert.Equal(token, result["facts"]!["record_token"]!.GetValue<string>());
        Assert.NotEmpty(result["facts"]!["not_available"]!.AsArray());
        Assert.Contains("employee_id", result["user_only_facts"]!.AsArray().Select(value => value!.GetValue<string>()));
        args["record_token"] = "not-a-stored-handle";
        var error = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke("employee_drill", args));
        Assert.Equal("not_calculated", error.Code);
    }

    [Fact]
    public async Task Visible_batch_reads_use_owner_queue_queries_and_absence_is_not_a_zero()
    {
        await using var fixture = await Start();
        var args = Args("run_batch");
        var prepared = await fixture.Invoke("run_batch_prepare", args);
        var commit = await fixture.Invoke("run_batch_commit", Commit(args,
            prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>(), "read-batch"));
        var id = commit["facts"]!["result"]!["batch_id"]!.GetValue<string>();
        var list = await fixture.Invoke("run_batch_list", new JsonObject());
        Assert.Contains(list["facts"]!["items"]!.AsArray(), row => row!["batch_id"]!.GetValue<string>() == id);
        var status = await fixture.Invoke("run_batch_status", new JsonObject { ["batch_id"] = id });
        Assert.Equal(id, status["facts"]!["batch_id"]!.GetValue<string>());
        Assert.Equal(0, status["facts"]!["progress"]!["done"]!.GetValue<int>());
        Assert.NotNull(status["facts"]!["failures"]);
        var unknown = await Assert.ThrowsAsync<CapabilityException>(() =>
            fixture.Invoke("run_batch_status", new JsonObject { ["batch_id"] = "not-stored" }));
        Assert.Equal("not_calculated", unknown.Code);
    }

    [Fact]
    public async Task Uncalculated_year_is_not_relabelled_as_a_zero_or_walkthrough()
    {
        await using var fixture = await Start();
        var args = new JsonObject { ["client_id"] = 1001, ["tax_year"] = 2022, ["state"] = "GA" };
        var eligibility = await fixture.Invoke("client_eligibility", args);
        Assert.False(eligibility["facts"]!["snapshot"]!["calculated"]!.GetValue<bool>());
        Assert.Null(eligibility["facts"]!["snapshot"]!["average_headcount"]);
        var error = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke("calc_walkthrough", args));
        Assert.Equal("not_calculated", error.Code);
    }

    [Theory]
    [InlineData("zero")]
    [InlineData("absent")]
    [InlineData("unavailable")]
    public async Task Counted_cohort_distinguishes_a_recorded_zero_missing_run_and_failed_storage(string state)
    {
        await using var fixture = await Start(services => services.AddScoped(_ =>
            CapabilityHarness.Proxy<IGoldReadPort>((method, _) => method.Name switch
            {
                "AtRisk" when state == "unavailable" => throw new SourceUnavailable(),
                "AtRisk" => new Dictionary<string, object?>
                {
                    ["run"] = state == "absent" ? null : new Dictionary<string, object?> { ["run_id"] = "synthetic-zero-run" },
                    ["counts"] = new Dictionary<string, object?> { ["eligible_count"] = 0L, ["evaluated"] = 5L },
                    ["rows"] = Array.Empty<IReadOnlyDictionary<string, object?>>(),
                },
                _ => throw new NotSupportedException(method.Name),
            })));
        var args = new JsonObject { ["client_id"] = 1001, ["tax_year"] = 2025, ["state"] = "GA" };
        if (state == "unavailable")
        {
            var failure = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke("client_at_risk", args));
            Assert.Equal("data_source_unavailable", failure.Code);
            return;
        }
        var result = await fixture.Invoke("client_at_risk", args);
        Assert.Equal(state == "zero", result["facts"]!["calculated"]!.GetValue<bool>());
        if (state == "zero")
        {
            Assert.Equal(0, result["facts"]!["eligible"]!.GetValue<int>());
            Assert.Equal(5, result["facts"]!["evaluated"]!.GetValue<int>());
            Assert.Equal(0, result["facts"]!["jobs_at_risk"]!.GetValue<double>());
            Assert.False(result.ContainsKey("user_only_facts"));
        }
    }

    [Fact]
    public async Task Ordinary_capability_http_route_exposes_real_bound_facts_and_provenance()
    {
        await using var fixture = await Start();
        var token = await RuntimeRequests.Mint(fixture.Host, new { oid = Writer.Oid });
        using var response = await RuntimeRequests.Send(fixture.Host, token, "/api/capabilities/simulate",
            HttpMethod.Post, new { args = new { client_id = 1001, tax_year = 2025, worksite_id = "GA_ATL_HQ" } });
        Assert.Equal(200, (int)response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>();
        Assert.Equal(result.GetProperty("facts").GetProperty("run_id").GetString(),
            result.GetProperty("provenance").GetProperty("run_id").GetString());
        Assert.Equal("tcc_gold", result.GetProperty("provenance").GetProperty("source").GetString());
    }

    private static JsonObject JsonSerializerNode(object value) =>
        System.Text.Json.JsonSerializer.SerializeToNode(TaxCredit.Application.Features.ClaimsArtifactsRules.FeatureValues.Wire(value))!.AsObject();
}
