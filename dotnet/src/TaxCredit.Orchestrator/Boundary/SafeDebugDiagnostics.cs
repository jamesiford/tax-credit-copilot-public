using System.Net;
using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Bounded diagnostic commands report observations, not credentials, response bodies or generated prose.</summary>
public sealed class SafeDebugDiagnostics : IDebugDiagnostics
{
    private readonly DiagnosticOptions options;
    private readonly IDiagnosticNetworkProbe network;
    private readonly ModelDiagnosticCall? model;
    private readonly TimeProvider clock;

    /// <summary>No live probe is silently installed; composition explicitly chooses each network/model adapter.</summary>
    public SafeDebugDiagnostics(DiagnosticOptions options, IDiagnosticNetworkProbe networkProbe,
        ModelDiagnosticCall? modelProbe = null, TimeProvider? timeProvider = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(networkProbe);
        this.options = options;
        network = networkProbe;
        model = modelProbe;
        clock = timeProvider ?? TimeProvider.System;
    }

    /// <inheritdoc />
    public async Task<JsonObject> RunNetcheckAsync(CancellationToken cancellationToken = default)
    {
        var start = clock.GetTimestamp();
        using var total = new CancellationTokenSource(options.TotalTimeout, clock);
        var targets = DiagnosticMetadata.AccountHosts(options.ProjectEndpoint?.AbsoluteUri).ToList();
        if (options.GatewayEndpoint is { } gateway)
        {
            targets.Add(new DiagnosticTarget(gateway.DnsSafeHost, "/channel/health"));
        }
        targets.Add(new DiagnosticTarget("login.microsoftonline.com"));
        targets.Add(new DiagnosticTarget("www.microsoft.com"));
        var reports = new JsonArray();
        foreach (var target in targets)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (Expired(total, start))
            {
                break;
            }
            reports.Add(await CheckHostAsync(target, total, start, cancellationToken).ConfigureAwait(false));
        }
        var report = new JsonObject
        {
            ["providers"] = DiagnosticMetadata.Strings(options.Providers),
            ["environment"] = options.Environment.DeepClone(),
            ["targets"] = reports,
        };
        if (Expired(total, start))
        {
            report["error"] = "timeout";
        }
        return report;
    }

    /// <inheritdoc />
    public async Task<JsonObject> RunModelProbeAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var report = new JsonObject
        {
            ["project_endpoint_host"] = options.ProjectEndpoint?.DnsSafeHost ?? "",
            ["model"] = options.Model,
            ["path"] = "injected_model_probe",
        };
        if (options.ProjectEndpoint is not { } endpoint || options.Model.Length == 0 || model is null)
        {
            report["ok"] = false;
            report["error"] = endpointMissing();
            return report;
        }
        var start = clock.GetTimestamp();
        using var total = new CancellationTokenSource(options.TotalTimeout, clock);
        var attempt = await AttemptAsync(token => model(endpoint, options.Model, token),
            total, start, cancellationToken).ConfigureAwait(false);
        report["ok"] = attempt.Error is null;
        report["ms"] = Elapsed(start);
        if (attempt.Error is not null)
        {
            report["error"] = attempt.Error;
            report["cause"] = attempt.Cause;
            return report;
        }
        if (attempt.Value is not { } observation || observation.ReplyCharacters is < 0 or > 1_000_000)
        {
            report["ok"] = false;
            report["error"] = "invalid_probe_metadata";
            return report;
        }
        report["reply_chars"] = observation.ReplyCharacters;
        report["base_url"] = observation.BaseUri is { IsAbsoluteUri: true } uri && uri.Scheme == Uri.UriSchemeHttps
            ? uri.GetComponents(UriComponents.SchemeAndServer | UriComponents.Path, UriFormat.UriEscaped) : null;
        return report;

        string endpointMissing() => options.ProjectEndpoint is null || options.Model.Length == 0
            ? "FOUNDRY_PROJECT_ENDPOINT or the model name is not set" : "model_probe_not_configured";
    }

    private async Task<JsonObject> CheckHostAsync(DiagnosticTarget target, CancellationTokenSource total, long commandStart, CancellationToken caller)
    {
        var report = new JsonObject { ["host"] = target.Host };
        var resolved = await AttemptAsync(token => network.ResolveAsync(target.Host, token), total, commandStart, caller).ConfigureAwait(false);
        if (resolved.Error is not null)
        {
            report["resolve"] = resolved.Error;
            return report;
        }
        var addresses = resolved.Value!.Where(address => IPAddress.TryParse(address, out _)).Distinct(StringComparer.Ordinal).Take(16).ToArray();
        report["resolved"] = new JsonArray(addresses.Select(address => (JsonNode)new JsonObject
        {
            ["address"] = address,
            ["kind"] = DiagnosticMetadata.Classify(address),
        }).ToArray());
        var first = addresses.FirstOrDefault(address => !address.Contains(':', StringComparison.Ordinal)) ?? addresses.FirstOrDefault();
        if (first is null)
        {
            report["resolve"] = "no addresses";
            return report;
        }
        var start = clock.GetTimestamp();
        var tcp = await AttemptAsync(async token =>
        {
            await network.ConnectAsync(first, token).ConfigureAwait(false);
            return true;
        }, total, commandStart, caller).ConfigureAwait(false);
        report["tcp"] = new JsonObject { ["ok"] = tcp.Error is null, ["ms"] = Elapsed(start), ["address"] = first };
        if (tcp.Error is not null)
        {
            report["tcp"]!["error"] = tcp.Error;
            return report;
        }
        var tls = await AttemptAsync(token => network.TlsGetStatusAsync(target.Host, first, token), total, commandStart, caller).ConfigureAwait(false);
        report["tls_get_status"] = Status(tls);
        if (target.HttpPath is { } path)
        {
            var http = await AttemptAsync(token => network.HttpGetStatusAsync(
                new Uri(new UriBuilder(Uri.UriSchemeHttps, target.Host).Uri, path), token),
                total, commandStart, caller).ConfigureAwait(false);
            report["http_client_status"] = Status(http);
        }
        return report;
    }

    private async Task<Attempt<T>> AttemptAsync<T>(Func<CancellationToken, Task<T>> action,
        CancellationTokenSource total, long commandStart, CancellationToken caller)
    {
        caller.ThrowIfCancellationRequested();
        var remaining = options.TotalTimeout - clock.GetElapsedTime(commandStart);
        if (total.IsCancellationRequested || remaining <= TimeSpan.Zero)
        {
            total.Cancel();
            return new Attempt<T>(default, "timeout");
        }
        var totalLimited = remaining <= options.StepTimeout;
        using var step = new CancellationTokenSource(totalLimited ? remaining : options.StepTimeout, clock);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(step.Token, total.Token, caller);
        try
        {
            linked.Token.ThrowIfCancellationRequested();
            return new Attempt<T>(await action(linked.Token).WaitAsync(linked.Token).ConfigureAwait(false));
        }
        catch (OperationCanceledException) when (!caller.IsCancellationRequested)
        {
            if (totalLimited)
            {
                total.Cancel();
            }
            return new Attempt<T>(default, "timeout");
        }
#pragma warning disable CA1031 // Exceptions are diagnostic observations; only their types are permitted in output.
        catch (Exception exception) when (exception is not (OperationCanceledException or OutOfMemoryException))
        {
            return new Attempt<T>(default, exception.GetType().Name, exception.InnerException?.GetType().Name);
        }
#pragma warning restore CA1031
    }

    private long Elapsed(long start) => (long)clock.GetElapsedTime(start).TotalMilliseconds;
    private bool Expired(CancellationTokenSource total, long start) =>
        total.IsCancellationRequested || clock.GetElapsedTime(start) >= options.TotalTimeout;
    private static JsonValue Status(Attempt<int> attempt) => attempt.Error is not null ? JsonValue.Create(attempt.Error)! :
        attempt.Value is >= 100 and <= 599 ? JsonValue.Create(attempt.Value)! : JsonValue.Create("invalid_status")!;
    private sealed record Attempt<T>(T? Value, string? Error = null, string? Cause = null);
}
