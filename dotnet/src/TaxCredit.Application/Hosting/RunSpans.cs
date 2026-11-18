using System.Diagnostics;

namespace TaxCredit.Application.Hosting;

/// <summary>
/// Named timing spans for one client calculation. They ride on <see cref="ActivitySource"/>, so with no listener attached
/// (telemetry off) <see cref="Start"/> returns <c>null</c> after one volatile read and nothing is allocated or timed.
/// </summary>
public static class RunSpans
{
    /// <summary>The source name a tracer or profiler subscribes to.</summary>
    public const string SourceName = "TaxCredit.Run";

    private static readonly ActivitySource Source = new(SourceName);

    /// <summary>Starts a span, or returns null when nothing is listening; always dispose the result with <c>using</c>.</summary>
    /// <param name="name">A stable stage name such as <c>source.read</c>.</param>
    /// <returns>The activity, or null when no listener is attached.</returns>
    public static Activity? Start(string name) => Source.StartActivity(name);

    /// <summary>Whether anything is listening, so a caller can skip building an expensive tag.</summary>
    public static bool Enabled => Source.HasListeners();
}
