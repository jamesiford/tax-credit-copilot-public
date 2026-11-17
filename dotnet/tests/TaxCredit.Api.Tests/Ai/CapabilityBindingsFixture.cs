using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Api.Tests.Ai;

internal sealed class CapabilityBindingsFixture(TestHost host) : IAsyncDisposable
{
    internal TestHost Host => host;
    internal static readonly ApiPrincipal Writer = new(RuntimeRequests.Writer, "writer@example.test",
        "Synthetic writer", "00000000-0000-0000-0000-0000000000aa", Authenticated: true);
    internal static readonly ApiPrincipal Other = new(RuntimeRequests.Reader,
        "other@example.test", Authenticated: true);

    internal static async Task<CapabilityBindingsFixture> Start(Action<IServiceCollection>? services = null)
    {
        var host = await TestHost.Start(services: services, configuration: new Dictionary<string, string?> { ["AUTH_MODE"] = "entra" });
        await RuntimeRequests.Reset(host, "G1");
        var fixture = new CapabilityBindingsFixture(host);
        fixture.Read(provider => provider.GetRequiredService<IChannelStateRepository>()
            .Grant(new WriterGrant(Other.Oid!, "Synthetic other writer", "writer", "fixture", PyDateTime.FromIsoFormat("2026-01-15T12:00:00+00:00"))));
        return fixture;
    }

    internal async Task<JsonObject> Invoke(string tool, JsonObject arguments, ApiPrincipal? principal = null)
    {
        using var scope = host.App.Services.CreateScope();
        using var identity = scope.ServiceProvider.GetRequiredService<IApiPrincipalAccessor>().Push(principal ?? Writer);
        return await scope.ServiceProvider.GetRequiredService<CapabilityService>().InvokeAsync(tool, arguments);
    }

    internal T Read<T>(Func<IServiceProvider, T> action)
    {
        using var scope = host.App.Services.CreateScope();
        return action(scope.ServiceProvider);
    }

    internal static JsonObject Args(string change) => JsonNode.Parse(change switch
    {
        "finding_resolve" => """{"client_id":1001,"tax_year":2025,"finding_id":"synthetic-finding","resolution":"accept","note":"Reviewed"}""",
        "finding_reopen" => """{"client_id":1001,"finding_id":"synthetic-finding"}""",
        "claim_transition" => """{"client_id":1001,"program_code":"GA_JTC","tax_year":2025,"status":"proposed"}""",
        "claim_record" => """{"client_id":1001,"program_code":"GA_JTC","tax_year":2025,"status":"proposed"}""",
        "engagement_set" => """{"client_id":1001,"program_code":"GA_JTC","scope":"out_of_scope","note":"No mandate"}""",
        "base_year_set" => """{"client_id":1001,"unit_id":"GA_ATL_HQ","base_year":2024}""",
        "claim_package_create" => """{"client_id":1001,"tax_year":2025}""",
        "run_batch" => """{"scope":{"kind":"one","account_ids":[1001]},"kind":"calculate","tax_years":[2025]}""",
        _ => throw new ArgumentOutOfRangeException(nameof(change)),
    })!.AsObject();

    internal static JsonObject Commit(JsonObject args, string token, string key) => new()
    {
        ["arguments"] = args.DeepClone(),
        ["confirmation_token"] = token,
        ["idempotency_key"] = key,
    };

    internal string State(string change) => Read(provider => change switch
    {
        "finding_resolve" or "finding_reopen" => PyJson.Dumps(provider.GetRequiredService<IFindingRepository>()
            .History(1001, "synthetic-finding").Select(row => row.ToDict()).ToArray()),
        "claim_transition" or "claim_record" => PyJson.Dumps(provider.GetRequiredService<IClaimRepository>()
            .History(1001, "GA_JTC", 2025).Select(row => row.ToDict()).ToArray()),
        "engagement_set" => PyJson.Dumps(provider.GetRequiredService<IClaimRepository>().Engagements(1001).Select(row => row.ToDict()).ToArray()),
        "base_year_set" => provider.GetRequiredService<IManualOverrideRepository>().History(1001).Count.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "claim_package_create" => provider.GetRequiredService<IArtifactRepository>().Live(1001, "claim_package", 2025).Count.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "run_batch" => provider.GetRequiredService<IRunBatchRepository>().ListBatches(100, 0).Total.ToString(System.Globalization.CultureInfo.InvariantCulture),
        _ => throw new ArgumentOutOfRangeException(nameof(change)),
    });

    public ValueTask DisposeAsync() => host.DisposeAsync();
}
