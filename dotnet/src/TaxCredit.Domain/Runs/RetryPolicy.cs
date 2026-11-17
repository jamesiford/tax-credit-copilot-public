using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Runs;

/// <summary>The retry policy (Python <c>backoff_seconds</c>): which failures are transient is decided elsewhere; the domain owns only how long to wait.</summary>
public static class RetryPolicy
{
    /// <summary>The default <c>base</c> of Python's <c>backoff_seconds</c>.</summary>
    public const double DefaultBaseSeconds = 5.0;

    /// <summary>The default <c>cap</c> of Python's <c>backoff_seconds</c>.</summary>
    public const double DefaultCapSeconds = 120.0;

    /// <summary>
    /// Python <c>backoff_seconds</c>: <c>min(cap, base * 2 ** max(0, attempt - 1)) * (1 + 0.25 * jitter())</c>, always a float.
    /// </summary>
    /// <remarks>
    /// Deliberate seam: Python defaults <c>jitter</c> to the global <c>random.random</c> (the Mersenne Twister state), which is not
    /// ported; the caller supplies the value source, and the production worker passes <c>lambda: 0.0</c>. Whether <paramref name="baseSeconds"/>
    /// is an int or a float is observable: Python raises <c>OverflowError</c> when a float <c>base</c> meets <c>2 ** 1024</c> or more, while an
    /// int <c>base</c> multiplies exactly and is capped (production passes the int <c>RUN_BACKOFF_BASE_SECONDS</c>).
    /// </remarks>
    /// <param name="attempt">Attempts so far; anything below 1 waits like the first.</param>
    /// <param name="jitter">The jitter source, called once, after the exponential is computed.</param>
    /// <param name="baseSeconds">Python <c>base</c>; defaults to the float 5.0.</param>
    /// <param name="cap">Python <c>cap</c>.</param>
    /// <returns>Seconds to wait.</returns>
    /// <exception cref="PyOverflowError">When Python's int-to-float conversion of the exponential overflows.</exception>
    public static double BackoffSeconds(long attempt, Func<double> jitter, PyNumber? baseSeconds = null, double cap = DefaultCapSeconds)
    {
        ArgumentNullException.ThrowIfNull(jitter);
        var raw = Raw(attempt, baseSeconds ?? PyNumber.OfFloat(DefaultBaseSeconds), cap);
        return raw * (1 + (0.25 * jitter()));
    }

    // min(cap, base * 2 ** k): Python's min keeps the first argument unless a later one is strictly smaller.
    private static double Raw(long attempt, PyNumber baseSeconds, double cap)
    {
        var k = attempt <= 1 ? 0 : (int)Math.Min(attempt - 1, 5000);
        if (!baseSeconds.IsInt)
        {
            // float * int converts the int first, and 2 ** 1024 does not fit a double.
            return k >= 1024 ? throw new PyOverflowError("int too large to convert to float") : PyArith.Min(cap, baseSeconds.FloatValue * Math.ScaleB(1.0, k));
        }

        var x = baseSeconds.IntValue == 0 ? 0.0 : Math.ScaleB((double)baseSeconds.IntValue, k);
        if (double.IsInfinity(x))
        {
            // The exact int is beyond a double. It wins the min only when it is below the cap, and then multiplying it by a float overflows.
            var wins = x > 0 ? double.IsPositiveInfinity(cap) : !double.IsNaN(cap) && !double.IsNegativeInfinity(cap);
            return wins ? throw new PyOverflowError("int too large to convert to float") : cap;
        }

        return PyArith.Min(cap, x);
    }
}
