using System.Runtime.CompilerServices;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>One request-scoped state suppresses repeated outage notices across several narrative steps.</summary>
public sealed class DegradationState
{
    private int _notified;
    /// <summary>Atomically claims this request's single unavailable notification.</summary>
    public bool NotifyOnce() => Interlocked.Exchange(ref _notified, 1) == 0;
}
/// <summary>Renders unchanged trusted JSON leaves when narration is unavailable or interrupted.</summary>
public static class ScriptedDegradation
{
    /// <summary>The standard complete-outage sentence.</summary>
    public const string Unavailable = "The assistant is unavailable; here are the engine's figures.";
    /// <summary>The standard partial-output sentence.</summary>
    public const string Interrupted = "The assistant was interrupted; the engine's figures follow.";
    /// <summary>The standard injection-refusal sentence.</summary>
    public const string InjectionBlocked = "This request was not sent to the assistant; here are the engine's figures.";
    /// <summary>Flattens supplied values without calculations and explicitly names truncated leaves.</summary>
    public static string Figures(JsonElement? facts, int maxLines = 30)
    {
        if (facts is null)
        {
            return "";
        }

        var leaves = Leaves(facts.Value, "").ToArray();
        var lines = leaves.Take(maxLines).Select(p => $"- {p.Path}: {p.Value}").ToList();
        if (leaves.Length > maxLines)
        {
            lines.Add($"- … and {leaves.Length - maxLines} more on the page.");
        }

        return string.Join("\n", lines);
    }
    private static IEnumerable<(string Path, string Value)> Leaves(JsonElement node, string path)
    {
        if (node.ValueKind == JsonValueKind.Object)
        {
            foreach (var prop in node.EnumerateObject())
            {
                foreach (var leaf in Leaves(prop.Value, path == "" ? prop.Name : $"{path}.{prop.Name}"))
                {
                    yield return leaf;
                }
            }
        }
        else if (node.ValueKind == JsonValueKind.Array)
        {
            int i = 0;
            foreach (var child in node.EnumerateArray())
            {
                i++;
                foreach (var leaf in Leaves(child, $"{path}[{i}]"))
                {
                    yield return leaf;
                }
            }
        }
        else if (node.ValueKind != JsonValueKind.Null)
        {
            yield return (path, node.ValueKind == JsonValueKind.String ? node.GetString()! : node.GetRawText());
        }
    }
    /// <summary>Falls back on typed model failures, never on caller cancellation.</summary>
    public static async IAsyncEnumerable<ModelEvent> StreamAsync(IAgentRuntime runtime, NarrationRequest request,
        DegradationState state, IAiTelemetry? telemetry = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        bool produced = false;
        await using var events = runtime.StreamAsync(request, cancellationToken).GetAsyncEnumerator(cancellationToken);
        ModelException? failure;
        while (true)
        {
            var (Moved, Error) = await NextAsync(events).ConfigureAwait(false);
            failure = Error;
            if (!Moved)
            {
                break;
            }

            produced |= events.Current is TextDelta { Text.Length: > 0 };
            yield return events.Current;
        }
        if (failure is null)
        {
            yield break;
        }

        telemetry?.Count("ai.degraded", provider: runtime.Name);
        string sentence = failure.Kind == ModelErrorKind.InjectionBlocked ? InjectionBlocked : produced ? Interrupted : Unavailable;
        var parts = new List<string>();
        if (state.NotifyOnce())
        {
            parts.Add(sentence);
        }

        string figures = Figures(request.TrustedFacts);
        if (figures.Length != 0)
        {
            parts.Add(figures);
        }
        else if (request.CallerFallback is { } fallback)
        {
            parts.Add(fallback());
        }

        if (parts.Count > 0)
        {
            yield return new TextDelta((produced ? "\n\n" : "") + string.Join("\n\n", parts));
        }

        yield return new StreamEnd("scripted", Hops: failure.Hops, FinishReason: produced ? "interrupted" : "degraded");
    }
    private static async Task<(bool Moved, ModelException? Error)> NextAsync(IAsyncEnumerator<ModelEvent> events)
    {
        try { return (await events.MoveNextAsync().ConfigureAwait(false), null); }
        catch (ModelException error) { return (false, error); }
    }
}
