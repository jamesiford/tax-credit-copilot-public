using System.Globalization;

namespace TaxCredit.Deployment.Telemetry;

internal sealed class Measurement
{
    private readonly object _gate = new();
    private long _count;
    private double _sum;
    private string _start = SafeSignals.Nano(DateTime.UtcNow);

    internal void Add(double number)
    {
        lock (_gate)
        {
            if (double.IsFinite(_sum + number))
            {
                _count++;
                _sum += number;
            }
        }
    }

    internal object? Take(string instrument)
    {
        lock (_gate)
        {
            if (_count == 0) { return null; }
            var now = SafeSignals.Nano(DateTime.UtcNow);
            // A distribution of raw measurements, not a reconstruction of SDK counter temporality.
            var result = new
            {
                name = "tcc.deployment.measurement." + instrument,
                histogram = new
                {
                    aggregationTemporality = 1,
                    dataPoints = new[]
                    {
                        new
                        {
                            startTimeUnixNano = _start, timeUnixNano = now,
                            count = _count.ToString(CultureInfo.InvariantCulture),
                            sum = _sum, bucketCounts = new[] { _count.ToString(CultureInfo.InvariantCulture) },
                            explicitBounds = Array.Empty<double>()
                        }
                    }
                }
            };
            _count = 0;
            _sum = 0;
            _start = now;
            return result;
        }
    }
}
