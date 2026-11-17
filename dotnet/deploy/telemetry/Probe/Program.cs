using System.Diagnostics;
using System.Diagnostics.Metrics;
using TaxCredit.ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();
builder.Logging.ClearProviders();
builder.Services.AddHttpClient();
var app = builder.Build();
using var source = new ActivitySource("TaxCredit.Ai");
using var unknown = new ActivitySource("Unapproved.Secret");
using var meter = new Meter("TaxCredit.Ai");
using var unknownMeter = new Meter("Unapproved.Secret");
var retries = meter.CreateCounter<long>("ai.retries");
var unrelated = unknownMeter.CreateCounter<long>("ai.retries");
var duration = meter.CreateHistogram<double>("gen_ai.client.operation.duration");
var usage = meter.CreateHistogram<long>("gen_ai.client.token.usage");
var forbidden = meter.CreateCounter<long>("private.person");
const string poison = "SYNTHETIC_PRIVATE_SENTINEL";
app.MapGet("/ready", () => Results.Ok());
app.MapGet("/subscriptions", () => Results.Json(new
{
    custom_trace = source.HasListeners(),
    custom_meter = retries.Enabled
}));
app.MapGet("/" + poison, async (IHttpClientFactory clients) =>
{
    using var span = source.StartActivity(poison, ActivityKind.Client);
    span?.SetTag("url.full", poison);
    span?.SetTag("person.id", poison);
    span?.SetTag("gen_ai.prompt", poison);
    span?.SetTag("authorization", poison);
    span?.SetBaggage("person.id", poison);
    span?.SetStatus(ActivityStatusCode.Error, poison);
    span?.AddEvent(new ActivityEvent(poison));
    using (unknown.StartActivity(poison)) { }
    retries.Add(1, new KeyValuePair<string, object?>("person.id", poison));
    unrelated.Add(1000);
    duration.Record(0.125, new KeyValuePair<string, object?>("gen_ai.request.model", poison));
    duration.Record(double.NaN);
    duration.Record(double.PositiveInfinity);
    usage.Record(3, new KeyValuePair<string, object?>("person.id", poison));
    forbidden.Add(123, new KeyValuePair<string, object?>("secret", poison));
    var downstream = Environment.GetEnvironmentVariable("PROBE_DEPENDENCY");
    if (downstream is not null)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(downstream + "/" + poison + "?q=" + poison));
        request.Headers.Add("X-Private", poison);
        request.Content = new StringContent(poison);
        using var response = await clients.CreateClient().SendAsync(request);
        response.EnsureSuccessStatusCode();
    }
    return Results.Ok();
});
app.MapPost("/stop", (IHostApplicationLifetime lifetime) =>
{
    lifetime.StopApplication();
    return Results.Ok();
});
await app.RunAsync();
