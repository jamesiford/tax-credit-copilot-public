namespace TaxCredit.Deployment.Telemetry;

internal static class Payloads
{
    private static object Resource(Settings settings) => new
    {
        attributes = new[]
        {
            new { key = "service.name", value = new { stringValue = settings.Service } },
            new { key = "service.version", value = new { stringValue = settings.Version } }
        }
    };

    internal static object Traces(Settings settings, List<object> spans) => new
    {
        resourceSpans = new[]
        {
            new
            {
                resource = Resource(settings),
                scopeSpans = new[] { new { scope = new { name = "TaxCredit.Deployment" }, spans } }
            }
        }
    };

    internal static object Metrics(Settings settings, object[] metrics) => new
    {
        resourceMetrics = new[]
        {
            new
            {
                resource = Resource(settings),
                scopeMetrics = new[] { new { scope = new { name = "TaxCredit.Deployment" }, metrics } }
            }
        }
    };
}
