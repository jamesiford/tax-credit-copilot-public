using System.Collections.Concurrent;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Runtime.InteropServices;

namespace TaxCredit.Deployment.Telemetry;

internal sealed class Agent : IDisposable
{
    private const int Capacity = 2048;
    private readonly ConcurrentQueue<object> _spans = new();
    private readonly ConcurrentDictionary<string, Measurement> _metrics = new(StringComparer.Ordinal);
    private readonly ActivityListener _activities;
    private readonly MeterListener _meters = new();
    private readonly Transport _transport = new();
    private readonly Settings _settings;
    private readonly Timer _timer;
    private readonly PosixSignalRegistration? _termination;
    private readonly object _exportLock = new();
    private readonly AsyncLocal<bool> _exporting = new();
    private int _queued;
    private bool _disposed;

    internal Agent(Settings settings)
    {
        _settings = settings;
        _activities = new ActivityListener
        {
            ShouldListenTo = source => SafeSignals.Source(source.Name),
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                _exporting.Value ? ActivitySamplingResult.None : ActivitySamplingResult.AllDataAndRecorded,
            SampleUsingParentId = (ref ActivityCreationOptions<string> _) =>
                _exporting.Value ? ActivitySamplingResult.None : ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = Capture
        };
        ActivitySource.AddActivityListener(_activities);
        _meters.InstrumentPublished = (instrument, listener) =>
        {
            if (SafeSignals.Instrument(instrument.Meter.Name, instrument.Name))
            {
                listener.EnableMeasurementEvents(instrument);
            }
        };
        _meters.SetMeasurementEventCallback<double>(Record);
        _meters.SetMeasurementEventCallback<long>(Record);
        _meters.SetMeasurementEventCallback<int>(Record);
        _meters.Start();
        _timer = new Timer(_ => Flush(), null, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(2));
        AppDomain.CurrentDomain.ProcessExit += (_, _) => Dispose();
        if (!OperatingSystem.IsWindows())
        {
            _termination = PosixSignalRegistration.Create(PosixSignal.SIGTERM, _ => Flush());
        }
    }

    public void Dispose()
    {
        _timer.Dispose();
        lock (_exportLock)
        {
            if (_disposed) { return; }
            Flush();
            _disposed = true;
            _activities.Dispose();
            _meters.Dispose();
            _transport.Dispose();
        }
        _termination?.Dispose();
    }

    private void Capture(Activity activity)
    {
        if (_exporting.Value)
        {
            return;
        }
        if (Interlocked.Increment(ref _queued) <= Capacity)
        {
            _spans.Enqueue(SafeSignals.Span(activity));
        }
        else
        {
            Interlocked.Decrement(ref _queued);
        }
    }

    private void Record<T>(Instrument instrument, T value, ReadOnlySpan<KeyValuePair<string, object?>> tags,
        object? state) where T : struct, IConvertible
    {
        if (_exporting.Value)
        {
            return;
        }
        var number = value.ToDouble(System.Globalization.CultureInfo.InvariantCulture);
        if (double.IsFinite(number) && number >= 0)
        {
            _metrics.GetOrAdd(instrument.Name, _ => new Measurement()).Add(number);
        }
    }

    private void Flush()
    {
        // A timer export is bounded to 1.5s, so exit waits at most one export plus its own.
        lock (_exportLock)
        {
            if (_disposed) { return; }
            _exporting.Value = true;
            try
            {
                List<object> spans = [];
                while (_spans.TryDequeue(out var span))
                {
                    Interlocked.Decrement(ref _queued);
                    spans.Add(span);
                    if (spans.Count == Capacity) { break; }
                }
                if (spans.Count != 0)
                {
                    _transport.Send(_settings.Endpoint, "v1/traces", Payloads.Traces(_settings, spans));
                }
                var metrics = _metrics.Select(pair => pair.Value.Take(pair.Key))
                    .OfType<object>().ToArray();
                if (metrics.Length != 0)
                {
                    _transport.Send(_settings.Endpoint, "v1/metrics", Payloads.Metrics(_settings, metrics));
                }
            }
            finally { _exporting.Value = false; }
        }
    }

}
