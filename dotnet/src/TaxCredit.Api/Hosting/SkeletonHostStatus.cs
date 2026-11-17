using TaxCredit.Application.Features.Framework;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Hosting;

/// <summary>Only the hermetic empty adapter set is ready; production awaits real startup-check adapters.</summary>
public sealed class SkeletonHostStatus(IRuntimeConfiguration configuration, IConfiguration startup) : IHostStatus
{
    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> Health => new Dictionary<string, object?>(StringComparer.Ordinal)
    {
        ["status"] = "ok",
        ["phase"] = 2,
        ["foundry_configured"] = !string.IsNullOrEmpty(configuration.Get("FOUNDRY_PROJECT_ENDPOINT")),
        ["agents_registered"] = false,
        ["ai"] = new
        {
            state = "disabled",
            providers = new[] { new { name = "foundry", state = "disabled", detail = "FOUNDRY_PROJECT_ENDPOINT is not set" } },
            agents_published = 0,
        },
        ["telemetry_configured"] = !string.IsNullOrEmpty(configuration.Get("APPLICATIONINSIGHTS_CONNECTION_STRING")),
        ["warm"] = new { status = "skipped" },
    };

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> Readiness
    {
        get
        {
            var hermetic = startup["TCC_CONTRACT_HOOKS"] == "1";
            return new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                ["ready"] = hermetic,
                ["warm"] = new { status = "skipped" },
                ["ai"] = "disabled",
                ["stores"] = new { status = hermetic ? "ready" : "unknown", problems = Array.Empty<object>(), warnings = Array.Empty<object>() },
                ["source_schema"] = new
                {
                    status = hermetic ? "skipped" : "unknown",
                    reads = new
                    {
                        tables = new Dictionary<string, object>(StringComparer.Ordinal),
                        cache = new { hits = 0, misses = 0, negative_hits = 0, evictions = 0, single_flight_waits = 0 },
                        rows = 0,
                        bytes = 0,
                    },
                },
            };
        }
    }
}
