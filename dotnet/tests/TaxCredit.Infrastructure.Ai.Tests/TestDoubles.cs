using System.Runtime.CompilerServices;
using System.Text;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Tests;

internal static class TestStreams
{
    public static readonly AgentSpec Spec = new("test-agent", "Narrate supplied facts.");
    public static NarrationRequest Request(string prompt = "Brief.", string principal = "test-user") => new(Spec, prompt, principal);
    public static async Task<List<ModelEvent>> Collect(IAsyncEnumerable<ModelEvent> stream)
    {
        var events = new List<ModelEvent>();
        await foreach (var item in stream)
        {
            events.Add(item);
        }

        return events;
    }
    public static string Text(IEnumerable<ModelEvent> events) => string.Concat(events.OfType<TextDelta>().Select(e => e.Text));
}
internal sealed class ScriptRuntime(string name, params object[][] attempts) : IAgentRuntime
{
    private int _calls;
    public int Calls => _calls;
    public string Name => name;
    public bool Ready { get; set; } = true;
    public bool ReadyFor(string agentName) => Ready;
    public string? VersionOf(string agentName) => "test-version";
    public ProviderStatus Status() => new(Name, Ready ? ProviderState.Ready : ProviderState.Disabled);
    public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        int index = Interlocked.Increment(ref _calls) - 1;
        object[] script = attempts[Math.Min(index, attempts.Length - 1)];
        await Task.Yield();
        foreach (object item in script)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (item is Exception error)
            {
                throw error;
            }

            if (item is TimeSpan delay) { await Task.Delay(delay, cancellationToken); continue; }
            yield return item is string text ? new TextDelta(text) : (ModelEvent)item;
        }
    }
}
internal sealed class FakeHttp(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
{
    public int Calls { get; private set; }
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Calls++;
        return send(request, cancellationToken);
    }
    public static HttpResponseMessage Sse(string payload) => new(System.Net.HttpStatusCode.OK)
    { Content = new StringContent(payload, Encoding.UTF8, "text/event-stream") };
    public static HttpResponseMessage Json(string payload) => new(System.Net.HttpStatusCode.OK)
    { Content = new StringContent(payload, Encoding.UTF8, "application/json") };
}
internal sealed class FakeTime : TimeProvider
{
    private DateTimeOffset _utc = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
    private long _timestamp;
    public override DateTimeOffset GetUtcNow() => _utc;
    public override long GetTimestamp() => _timestamp;
    public override long TimestampFrequency => TimeSpan.TicksPerSecond;
    public void Advance(TimeSpan duration) { _utc += duration; _timestamp += duration.Ticks; }
}
internal sealed class Collector : IAiTelemetry
{
    public List<AiCallInfo> Starts { get; } = [];
    public List<AiCallResult> Results { get; } = [];
    public List<string> Counts { get; } = [];
    public IAiCallSpan StartCall(AiCallInfo info) { Starts.Add(info); return new Span(this); }
    public void Count(string metric, long value = 1, string? provider = null, string? scope = null) => Counts.Add(metric);
    private sealed class Span(Collector owner) : IAiCallSpan
    {
        public void Finish(AiCallResult result) => owner.Results.Add(result);
    }
}
