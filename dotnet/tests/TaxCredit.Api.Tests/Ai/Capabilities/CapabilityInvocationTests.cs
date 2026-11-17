using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

public sealed class CapabilityInvocationTests
{
    [Fact]
    public async Task Dependency_injection_retains_the_complete_catalogue_and_integral_JSON_is_invokable()
    {
        using var harness = new CapabilityHarness();
        Assert.Equal(36, harness.Service.List()["tools"]!.AsArray().Count);
        var result = await harness.Service.InvokeAsync("client_situation",
            JsonNode.Parse("""{"client_id":42.0,"year":2025.0}""")!.AsObject());
        Assert.False(result["facts"]!["assessed"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Direct_claim_reads_use_the_certified_domain_and_never_the_missing_sibling()
    {
        using var harness = new CapabilityHarness();
        harness.Read = (_, _) => throw new InvalidOperationException("A direct read must not use a sibling.");
        harness.Claims.Add(ProgramClaim.Create(new ClaimSpec
        {
            ClientId = 42,
            ProgramCode = "GA_JTC",
            TaxYear = 2025,
            IdentifiedUsd = "12345.6700",
            AverageHeadcount = 25,
            BaseAverageHeadcount = 20,
            ThresholdJobs = 2,
            Status = ClaimStatus.Assessed,
            Provenance = Provenance.Computed,
        }));
        var situation = await harness.Service.InvokeAsync("client_situation", new JsonObject { ["client_id"] = 42 });
        Assert.Equal("12345.6700", situation["facts"]!["identified_usd"]!.GetValue<string>());
        Assert.Equal("Synthetic Retail", situation["facts"]!["client_name"]!.GetValue<string>());
        Assert.Contains("$12,345.67", situation["blocks"]!.ToJsonString());
        Assert.Null(situation["provenance"]!["run_id"]);
        var history = await harness.Service.InvokeAsync("claim_cell_history",
            new JsonObject { ["client_id"] = 42, ["program_code"] = "ga_jtc", ["tax_year"] = 2025 });
        Assert.Single(history["facts"]!["history"]!.AsArray());
        Assert.Equal("GA_JTC", history["facts"]!["current"]!["program_code"]!.GetValue<string>());
    }

    [Fact]
    public async Task Unassessed_and_missing_history_are_not_zero_and_no_fake_figure_is_returned()
    {
        using var harness = new CapabilityHarness();
        var situation = await harness.Service.InvokeAsync("client_situation", new JsonObject { ["client_id"] = 42, ["year"] = 2025 });
        Assert.False(situation["facts"]!["assessed"]!.GetValue<bool>());
        Assert.Null(situation["facts"]!["identified_usd"]);
        var trend = await harness.Service.InvokeAsync("client_trend", new JsonObject { ["client_id"] = 42 });
        Assert.False(trend["facts"]!["calculated"]!.GetValue<bool>());
        var error = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_cell_history",
            new JsonObject { ["client_id"] = 42, ["program_code"] = "GA_JTC", ["tax_year"] = 2025 }));
        Assert.Equal("not_calculated", error.Code);
    }

    [Fact]
    public async Task Missing_sibling_is_explicit_and_unexpected_failure_does_not_disclose_messages()
    {
        using var harness = new CapabilityHarness();
        var missing = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("book_rank", []));
        Assert.Equal(503, missing.StatusCode);
        harness.Read = (_, args) =>
        {
            Assert.Equal(8, args["limit"]!.GetValue<int>());
            throw new InvalidOperationException("not for a client to see");
        };
        var failure = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("book_rank", []));
        Assert.Equal("internal_error", failure.Code);
        Assert.DoesNotContain("not for a client", failure.Body().ToJsonString());
    }

    [Fact]
    public async Task All_nested_clients_are_authorized_before_any_dispatch()
    {
        using var harness = new CapabilityHarness();
        harness.Read = (_, _) => throw new InvalidOperationException("not reached");
        var call = new JsonObject { ["scope"] = new JsonObject { ["kind"] = "list", ["client_ids"] = new JsonArray(42, 999) } };
        var denied = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("run_batch_prepare", call));
        Assert.Equal("client_not_authorized", denied.Code);
        Assert.Equal(403, denied.StatusCode);
        Assert.Empty(harness.Confirmations.Rows);
        Assert.Equal(new long[] { 42, 43 }, CapabilityService.ClientIds(
            JsonNode.Parse("""{"arguments":{"account_id":42,"scope":{"account_ids":[43,true,"99"]}}}""")!.AsObject()).Order());
    }

    [Fact]
    public async Task Resolver_filters_unentitled_candidates_and_never_guesses_between_shared_aliases()
    {
        using var harness = new CapabilityHarness();
        harness.AllowedClients.Remove(43);
        var resolved = await harness.Service.InvokeAsync("client_resolve", new JsonObject { ["name_or_text"] = "Synthetic Retail" });
        Assert.Equal(42, resolved["facts"]!["client_id"]!.GetValue<long>());
        var missing = await harness.Service.InvokeAsync("client_resolve", new JsonObject { ["name_or_text"] = "unknown" });
        Assert.Single(missing["facts"]!["candidates"]!.AsArray());
        Assert.DoesNotContain("Synthetic Foods", missing.ToJsonString());
    }

    [Fact]
    public async Task Unknown_person_lanes_are_refused_unless_first_party_or_a_writer()
    {
        using var harness = new CapabilityHarness();
        harness.Read = (_, _) => Task.FromResult(new CapabilityRead(new JsonObject { ["value"] = "hidden" },
            Blocks: [new JsonObject { ["kind"] = "paragraph", ["audience"] = "future-unknown", ["text"] = "hidden", ["rows"] = new JsonArray() }]));
        var denied = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_package_redeem",
            new JsonObject { ["ticket"] = "synthetic-ticket-value" }));
        Assert.Equal("employee_level_not_allowed", denied.Code);
        using var scope = harness.Principals.Push(new ApiPrincipal(Oid: "service", PrincipalType: "agent",
            ActingFor: new ActingUser("reader", Channel: "teams")));
        var result = await harness.Service.InvokeAsync("claim_package_redeem", new JsonObject { ["ticket"] = "synthetic-ticket-value" });
        Assert.Equal("hidden", result["facts"]!["value"]!.GetValue<string>());
    }

    [Fact]
    public async Task Queries_are_registered_for_the_existing_mediator()
    {
        using var harness = new CapabilityHarness();
        var list = harness.Services.GetRequiredService<IRequestHandler<ListCapabilitiesQuery, JsonObject>>();
        Assert.NotEmpty((await list.Handle(new ListCapabilitiesQuery(), CancellationToken.None))["tools"]!.AsArray());
        var invoke = harness.Services.GetRequiredService<IRequestHandler<InvokeCapabilityQuery, JsonObject>>();
        Assert.False((await invoke.Handle(new InvokeCapabilityQuery("client_situation", new JsonObject { ["client_id"] = 42 }),
            CancellationToken.None))["facts"]!["assessed"]!.GetValue<bool>());
    }
}
