using System.Diagnostics;
using System.Diagnostics.Metrics;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Infrastructure.Ai.Telemetry;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class TelemetryTests
{
    [Fact]
    public async Task ObserverRecordsSuccessErrorRefusalAndAbandonment()
    {
        var collector = new Collector();
        var runtime = new ObservedRuntime(new ScriptRuntime("test", ["abcd", new ModelUsage(2, 1), new StreamEnd("test", Hops: ["one", "test"])]), collector);
        await TestStreams.Collect(runtime.StreamAsync(TestStreams.Request()));
        Assert.Equal("ok", Assert.Single(collector.Results).Outcome);
        Assert.Equal(new ModelUsage(2, 1), collector.Results[0].Usage);
        Assert.Equal(4, collector.Results[0].OutputChars);
        Assert.True(collector.Results[0].End!.FallbackUsed);
        var refused = new ObservedRuntime(new GuardedRuntime(new ScriptRuntime("gateway", ["never"]),
            new EgressGuard(EgressPolicy.BlockExternal)), collector);
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(refused.StreamAsync(TestStreams.Request())));
        Assert.Equal("error", collector.Results[^1].Outcome);
        Assert.Equal("EgressRefused", collector.Results[^1].ErrorType);
        await using (var iterator = runtime.StreamAsync(TestStreams.Request()).GetAsyncEnumerator())
        {
            Assert.True(await iterator.MoveNextAsync());
        }

        Assert.Equal("abandoned", collector.Results[^1].Outcome);
    }
    [Fact]
    public async Task CallerCancellationRecordsCancelledWithoutOutage()
    {
        var collector = new Collector();
        var runtime = new ObservedRuntime(new ScriptRuntime("test", [TimeSpan.FromMinutes(1)]), collector);
        using var stop = new CancellationTokenSource(TimeSpan.FromMilliseconds(20));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(runtime.StreamAsync(TestStreams.Request(), stop.Token)));
        Assert.Equal("cancelled", Assert.Single(collector.Results).Outcome);
    }
    [Fact]
    public void ActivityAndMeterEmitOnlyShapeAndRegisteredDimensions()
    {
        var finished = new List<Activity>();
        var measurements = new List<string>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == "test.ai",
            Sample = (ref _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity => finished.Add(activity)
        };
        ActivitySource.AddActivityListener(listener);
        using var meterListener = new MeterListener
        {
            InstrumentPublished = (instrument, receiver) =>
            {
                if (instrument.Meter.Name == "test.ai")
                {
                    receiver.EnableMeasurementEvents(instrument);
                }
            }
        };
        meterListener.SetMeasurementEventCallback<long>((instrument, value, tags, _) =>
            measurements.Add(instrument.Name + ":" + value + ":" + string.Join(",", tags.ToArray().Select(t => t.Value))));
        meterListener.SetMeasurementEventCallback<double>((instrument, value, tags, _) =>
            measurements.Add(instrument.Name + ":" + value + ":" + string.Join(",", tags.ToArray().Select(t => t.Value))));
        meterListener.Start();
        using var source = new ActivitySource("test.ai");
        using var meter = new Meter("test.ai");
        using var telemetry = new ActivityAiTelemetry(["test", "test-agent", "test-model", "v1"], activities: source, meter: meter);
        var span = telemetry.StartCall(new(ModelRole.Narrator, "test", "test-agent"));
        span.Finish(new("ok", new ModelUsage(4, 2), End: new("test", "test-model", "v1", ["test"], "stop"), PromptChars: 12, OutputChars: 8));
        span.Finish(new("error"));
        telemetry.Count("ai.retries", provider: "test");
        telemetry.Count("SENTINEL-PROMPT", provider: "SENTINEL-PRINCIPAL");
        var unknown = telemetry.StartCall(new(ModelRole.Router, "SENTINEL-ENDPOINT", "SENTINEL-PROMPT", "SENTINEL-SECRET"));
        unknown.Finish(new("error", ErrorType: "SENTINEL-BODY", End: new("test", "SENTINEL-MODEL", Hops: ["SENTINEL-ID"])));
        Assert.Equal(2, finished.Count);
        string recorded = string.Join("\n", finished.SelectMany(a => a.TagObjects).Select(p => $"{p.Key}:{p.Value}").Concat(measurements));
        Assert.DoesNotContain("SENTINEL", recorded, StringComparison.Ordinal);
        Assert.Contains("gen_ai.usage.input_tokens:4", recorded, StringComparison.Ordinal);
        Assert.Contains("gen_ai.client.operation.duration", recorded, StringComparison.Ordinal);
        Assert.Contains("gen_ai.client.token.usage", recorded, StringComparison.Ordinal);
        Assert.Contains("ai.retries", recorded, StringComparison.Ordinal);
    }
}
