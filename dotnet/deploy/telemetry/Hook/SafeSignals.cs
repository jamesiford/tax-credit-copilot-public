using System.Diagnostics;
using System.Globalization;

namespace TaxCredit.Deployment.Telemetry;

internal static class SafeSignals
{
    internal static bool Source(string name) => name is
        "Microsoft.AspNetCore" or "System.Net.Http" or "TaxCredit.Ai" or "TaxCredit.Orchestrator.Tools";

    internal static bool Instrument(string meter, string name) => (meter, name) switch
    {
        ("Microsoft.AspNetCore.Hosting", "http.server.request.duration") => true,
        ("System.Net.Http", "http.client.request.duration") => true,
        ("TaxCredit.Ai", "gen_ai.client.operation.duration" or "gen_ai.client.token.usage"
            or "ai.retries" or "ai.breaker_opens" or "ai.bulkhead_rejections" or "ai.budget_refusals"
            or "ai.injection_blocked" or "ai.egress_refusals" or "ai.degraded") => true,
        _ => false
    };

    internal static string Nano(DateTime utc) =>
        ((utc.Ticks - DateTime.UnixEpoch.Ticks) * 100).ToString(CultureInfo.InvariantCulture);

    internal static object Span(Activity activity) => new
    {
        traceId = activity.TraceId.ToHexString(),
        spanId = activity.SpanId.ToHexString(),
        parentSpanId = activity.ParentSpanId == default ? "" : activity.ParentSpanId.ToHexString(),
        name = activity.Source.Name + "." + activity.Kind,
        kind = (int)activity.Kind + 1,
        startTimeUnixNano = Nano(activity.StartTimeUtc),
        endTimeUnixNano = Nano(activity.StartTimeUtc + activity.Duration),
        status = new { code = activity.Status == ActivityStatusCode.Error ? 2 : 0 }
    };
}
