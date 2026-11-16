using System.Data.Common;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.Framework;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Health probes read settled observations; neither a hook flag nor configuration alone proves store readiness.</summary>
public sealed class RuntimeStatus(IServiceScopeFactory scopes, RuntimeConfiguration settings, ModelRouter models) : IHostStatus
{
    private IReadOnlyDictionary<string, object?> _readiness = new Dictionary<string, object?>(StringComparer.Ordinal) { ["ready"] = false };

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> Health => new Dictionary<string, object?>(StringComparer.Ordinal)
    {
        ["status"] = "ok",
        ["phase"] = 2,
        ["foundry_configured"] = !string.IsNullOrEmpty(settings.Get("FOUNDRY_PROJECT_ENDPOINT")),
        ["agents_registered"] = false,
        ["ai"] = new { state = AiState(), providers = models.Statuses().Select(p => new { name = p.Name, state = p.State.ToString().ToLowerInvariant(), detail = p.Detail }), agents_published = 0 },
        ["telemetry_configured"] = !string.IsNullOrEmpty(settings.Get("APPLICATIONINSIGHTS_CONNECTION_STRING")),
        ["warm"] = new { status = "skipped" },
    };

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> Readiness => Volatile.Read(ref _readiness);

    /// <summary>Called once at startup and after reset/configuration changes, outside probe requests.</summary>
    public void Settle()
    {
        using var scope = scopes.CreateScope();
        var provider = scope.ServiceProvider;
        var store = Observe(() => _ = provider.GetRequiredService<IRunBatchRepository>().QueueHealth(
            RuntimeCalculationRegistration.Instant(provider.GetRequiredService<Application.Ports.Contract.IClock>())));
        var accounts = 0;
        var source = Observe(() =>
        {
            var reader = provider.GetRequiredService<ISourceReader>();
            if (!reader.IsConfigured) { throw new SourceNotConfigured(); }
            accounts = reader.ListAccounts().Count;
        });
        Volatile.Write(ref _readiness, new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["ready"] = store is null && source is null,
            ["warm"] = new { status = "skipped" },
            ["ai"] = AiState(),
            ["stores"] = new { status = store is null ? "ready" : "unavailable", problems = store is null ? Array.Empty<string>() : [store], warnings = Array.Empty<string>() },
            ["source_schema"] = new { status = source is null ? "ready" : "unavailable", accounts, problem = source },
        });
    }

    private string AiState()
    {
        var states = models.Statuses().Select(p => p.State).ToArray();
        return states.All(s => s == ProviderState.Disabled) ? "disabled"
            : states.Any(s => s == ProviderState.Ready) ? "ready" : "unavailable";
    }

    private static string? Observe(Action read)
    {
        try { read(); return null; }
        catch (SourceFailureException e) { return e.Code; }
        catch (ApiAuthException e) { return e.Code; }
        catch (DbException) { return "store_unavailable"; }
        catch (IOException) { return "resource_unavailable"; }
    }
}
