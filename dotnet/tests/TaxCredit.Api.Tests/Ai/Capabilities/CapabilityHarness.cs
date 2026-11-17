using System.Reflection;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Endpoints.Ai;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

internal sealed class CapabilityHarness : IDisposable
{
    private readonly ServiceProvider _provider;
    internal readonly PrincipalContext Principals = new();
    internal readonly List<ProgramClaim> Claims = [];
    internal readonly List<SourceAccount> Accounts = [new(42, "Synthetic Retail"), new(43, "Synthetic Foods")];
    internal readonly List<GoldQuerySpec> Queries = [];
    internal readonly List<ChannelAuditEvent> Audit = [];
    internal readonly ConfirmationMemory Confirmations = new();
    internal readonly HashSet<long> AllowedClients = [42, 43];
    internal bool Writer { get; set; }
    internal Func<string, JsonObject, Task<CapabilityRead>>? Read { get; set; }
    internal Func<string, JsonObject, Task<JsonObject>>? Preview { get; set; }
    internal Func<string, JsonObject, Task<JsonObject>>? Commit { get; set; }
    internal GoldQueryResult QueryResult { get; set; } = new(["worksite_id", "row_count"],
        [new Dictionary<string, object?> { ["worksite_id"] = "UNIT-A", ["row_count"] = 8L }], false, false);
    internal IReadOnlyList<GoldQueryDataset> Datasets { get; set; } =
    [
        new("unit_year_master", "is_current", false, false,
        [
            new("worksite_id", "text", "dimension", "public_aggregate", ["count_distinct"], ["eq"]),
            new("annual_credit_usd", "decimal", "measure", "public_aggregate", ["sum"], ["gte"], "USD"),
        ]),
        new("employee_eligibility", "live_run", true, true,
        [
            new("record_token", "text", "identifier", "employee_level", ["count_distinct"], ["eq"]),
            new("worksite_id", "text", "dimension", "public_aggregate", ["count_distinct"], ["eq"]),
            new("tax_year", "int", "dimension", "public_aggregate", ["count_distinct"], ["eq"]),
            new("employee_id", "text", "identifier", "blocked", [], []),
        ]),
    ];

    internal CapabilityService Service { get; }
    internal IServiceProvider Services => _provider;

    internal CapabilityHarness(CapabilityCatalog? catalog = null, TimeProvider? clock = null, Action<CapabilityOptions>? options = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton<IApiPrincipalAccessor>(Principals);
        services.AddSingleton<IClientAuthorizer>(new ClientPolicy(this));
        services.AddSingleton<IWriterEntitlement>(new WriterEntitlement(this));
        services.AddSingleton<IWriterPolicy>(new WriterPolicy(this));
        services.AddSingleton(Proxy<ISourceReader>((method, _) => method.Name switch
        {
            "ListAccounts" => Accounts.ToArray(),
            "get_IsConfigured" => true,
            _ => throw new NotSupportedException(method.Name),
        }));
        services.AddSingleton(Proxy<IClaimRepository>(ClaimCall));
        services.AddSingleton(Proxy<IGoldReadPort>((method, _) => method.Name switch
        {
            "LatestRun" => null,
            "ClientYearSeries" => new Dictionary<string, object?> { ["run"] = null, ["years"] = Array.Empty<object>() },
            _ => throw new NotSupportedException(method.Name),
        }));
        services.AddSingleton(Proxy<IGoldDataQueryPort>((method, args) => method.Name switch
        {
            "Catalog" => Datasets,
            "Run" => Run((GoldQuerySpec)args![0]!),
            "DistinctValues" => QueryResult,
            _ => throw new NotSupportedException(method.Name),
        }));
        services.AddSingleton(Proxy<IChannelStateRepository>(Confirmations.Call));
        services.AddSingleton(Proxy<IChannelAuditRepository>((method, args) =>
        {
            if (method.Name == "Append" && args![0] is ChannelAuditEvent entry)
            {
                Audit.Add(entry);
                return null;
            }
            throw new NotSupportedException(method.Name);
        }));
        services.AddSingleton<ICapabilityReadBridge>(new ReadBridge(this));
        services.AddSingleton<ICapabilityWriteBridge>(new WriteBridge(this));
        if (catalog is not null) { services.AddSingleton(catalog); }
        if (clock is not null) { services.AddSingleton(clock); }
        services.AddCapabilityServices(options);
        services.AddAiCapabilityHandlers();
        _provider = services.BuildServiceProvider();
        Service = _provider.GetRequiredService<CapabilityService>();
    }

    private GoldQueryResult Run(GoldQuerySpec spec)
    {
        Queries.Add(spec);
        return QueryResult;
    }

    private object? ClaimCall(MethodInfo method, object?[]? args) => method.Name switch
    {
        "Coverage" => Claims.Where(claim => claim.ClientId == (long)args![0]! &&
            (args[2] is not IEnumerable<long> years || years.Contains(claim.TaxYear))).ToArray(),
        "Current" => Claims.LastOrDefault(claim => claim.ClientId == (long)args![0]! &&
            claim.ProgramCode == (string)args[1]! && claim.TaxYear == (long)args[2]!),
        "History" => Claims.Where(claim => claim.ClientId == (long)args![0]! &&
            claim.ProgramCode == (string)args[1]! && claim.TaxYear == (long)args[2]!).ToArray(),
        _ => throw new NotSupportedException(method.Name),
    };

    internal static T Proxy<T>(Func<MethodInfo, object?[]?, object?> handler) where T : class
    {
        var proxy = DispatchProxy.Create<T, PortProxy>();
        ((PortProxy)(object)proxy).Handler = handler;
        return proxy;
    }

    public void Dispose() => _provider.Dispose();

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1852:Seal internal types",
        Justification = "DispatchProxy generates a derived type at runtime.")]
    public class PortProxy : DispatchProxy
    {
        internal Func<MethodInfo, object?[]?, object?> Handler { get; set; } = null!;
        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args) => Handler(targetMethod!, args);
    }

    private sealed class ClientPolicy(CapabilityHarness harness) : IClientAuthorizer
    {
        public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult(harness.AllowedClients.Contains(clientId));
    }

    private sealed class WriterEntitlement(CapabilityHarness harness) : IWriterEntitlement
    {
        public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult(harness.Writer);
    }

    private sealed class WriterPolicy(CapabilityHarness harness) : IWriterPolicy
    {
        public ValueTask CheckAsync(ApiPrincipal principal, string? actor, bool requiresWriter, CancellationToken cancellationToken = default) =>
            harness.Writer ? ValueTask.CompletedTask :
                ValueTask.FromException(new AuthRefusalException(403, "writer_required", "Writer entitlement required."));
    }

    private sealed class ReadBridge(CapabilityHarness harness) : ICapabilityReadBridge
    {
        public Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken) =>
            harness.Read?.Invoke(capability, arguments) ?? throw CapabilityException.Missing("test sibling", capability);
    }

    private sealed class WriteBridge(CapabilityHarness harness) : ICapabilityWriteBridge
    {
        public Task<JsonObject> PreviewAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken) =>
            harness.Preview?.Invoke(change, arguments) ?? Task.FromResult(new JsonObject
            {
                ["before"] = null,
                ["after"] = new JsonObject { ["status"] = arguments["status"]?.DeepClone() },
            });
        public Task<JsonObject> CommitAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken) =>
            harness.Commit?.Invoke(change, arguments) ?? Task.FromResult(new JsonObject { ["status"] = arguments["status"]?.DeepClone() });
    }
}

internal sealed class PrincipalContext : IApiPrincipalAccessor
{
    private readonly AsyncLocal<ApiPrincipal?> _principal = new();
    public ApiPrincipal? Current => _principal.Value;
    public IDisposable Push(ApiPrincipal? principal)
    {
        var previous = Current;
        _principal.Value = principal;
        return new Scope(() => _principal.Value = previous);
    }
    private sealed class Scope(Action restore) : IDisposable
    {
        public void Dispose() => restore();
    }
}
