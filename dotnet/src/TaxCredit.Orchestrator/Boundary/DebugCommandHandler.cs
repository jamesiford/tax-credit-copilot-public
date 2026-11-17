using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Diagnostics must return bounded, sanitized metadata, never credentials, private headers or model replies.</summary>
public interface IDebugDiagnostics
{
    /// <summary>Probe configured network dependencies without forwarding a reader's credentials.</summary>
    Task<JsonObject> RunNetcheckAsync(CancellationToken cancellationToken = default);
    /// <summary>Report model connectivity metadata, not generated model text.</summary>
    Task<JsonObject> RunModelProbeAsync(CancellationToken cancellationToken = default);
}

/// <summary>Debug commands are text-handler decisions, not HTTP diagnostic endpoints.</summary>
public sealed partial class DebugCommandHandler
{
    private readonly IdentityOptions settings;
    private readonly IDebugDiagnostics? diagnostics;

    /// <summary>Construction warns once when explicitly enabled; no diagnostic implementation is implicitly activated.</summary>
    public DebugCommandHandler(IdentityOptions settings, IDebugDiagnostics? diagnostics = null,
        ILogger<DebugCommandHandler>? logger = null)
    {
        ArgumentNullException.ThrowIfNull(settings);
        this.settings = settings;
        this.diagnostics = diagnostics;
        if (settings.DebugWhoami)
        {
            WarnDebugEnabled(logger ?? Microsoft.Extensions.Logging.Abstractions.NullLogger<DebugCommandHandler>.Instance);
        }
    }

    /// <summary>Null means ordinary text, including every debug-looking command when the switch is off.</summary>
    public async Task<string?> TryHandleAsync(string text, IdentityContext context, DebugRuntimeState? runtime = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (!settings.DebugWhoami)
        {
            return null;
        }
        var command = text.Trim().ToLowerInvariant();
        if (command == "/whoami")
        {
            return IdentityPresenter.Whoami(context, settings, runtime);
        }
        if (command is not ("/netcheck" or "/modelprobe"))
        {
            return null;
        }
        if (diagnostics is null)
        {
            return new JsonObject { ["ok"] = false, ["error"] = "diagnostics_not_configured" }.ToJsonString();
        }
        var result = command == "/netcheck"
            ? await diagnostics.RunNetcheckAsync(cancellationToken).ConfigureAwait(false)
            : await diagnostics.RunModelProbeAsync(cancellationToken).ConfigureAwait(false);
        return result.ToJsonString();
    }

    [LoggerMessage(Level = LogLevel.Warning,
        Message = "CHANNEL_DEBUG_WHOAMI is ON: diagnostic commands are available. Disable after use; see docs/m365-channel/DEMO-CLEANUP.md.")]
    private static partial void WarnDebugEnabled(ILogger logger);
}
