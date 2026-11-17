using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Orchestrator.Composition;

/// <summary>One lane-projected, names-only payload for every model narration path.</summary>
public static class ModelBrief
{
    /// <summary>All narrator paths share this names-only projection, including the framework's tool responses.</summary>
    public static JsonObject Build(string question, IReadOnlyList<CompositionRun> runs, bool fenced = false)
    {
        var full = CompositionProjection.Index(CompositionProjection.Facts(runs, model: false));
        var facts = CompositionProjection.Facts(runs, model: true);
        var index = CompositionProjection.Index(facts);
        var hidden = CompositionProjection.HiddenText(full, index);
        var secrets = CompositionProjection.Secrets(runs);
        var paths = new JsonArray();
        foreach (var (path, value) in index.Leaves.OrderBy(pair => pair.Key, StringComparer.Ordinal))
        {
            if (value.ValueKind is JsonValueKind.Null or JsonValueKind.True or JsonValueKind.False ||
                !CompositionProjection.CanonicalPath(path))
            {
                continue;
            }
            var formatter = FactPlaceholders.Formatter(path, value);
            try
            {
                FactPlaceholders.Expand(FactPlaceholders.PlaceholderFor(path, formatter), index);
                paths.Add(new JsonObject
                {
                    ["path"] = path,
                    ["format"] = formatter,
                    ["placeholder"] = FactPlaceholders.PlaceholderFor(path, formatter),
                });
            }
            catch (PlaceholderException)
            {
                // Unrenderable evidence is never advertised as a usable placeholder.
            }
        }
        var notes = runs.Where(run => !CompositionProjection.HasUserLane(run))
            .SelectMany(run => run.Result.Warnings)
            .Where(note => !CompositionProjection.ContainsHiddenText(note, hidden) &&
                !CompositionProjection.ContainsHiddenText(note, secrets)).ToArray();
        var asked = CompositionProjection.ContainsHiddenText(question, hidden) ||
            CompositionProjection.ContainsHiddenText(question, secrets) ? "[reader question withheld]" : question;
        return new JsonObject
        {
            ["question"] = fenced ? Fence(asked, "reader question") : asked,
            ["tools"] = Strings(runs.Select(run => run.Name)),
            ["fact_paths"] = paths,
            ["notes"] = Strings(notes),
            ["declined"] = null,
        };
    }

    /// <summary>Only declared lookup tools receive actual structural values; ordinary results contain names, never values.</summary>
    public static JsonObject Answer(CompositionRun run, JsonObject brief)
    {
        var paths = brief["fact_paths"] as JsonArray ?? [];
        var answer = new JsonObject
        {
            ["ok"] = true,
            ["tool"] = run.Name,
            ["fact_paths"] = new JsonArray(paths.OfType<JsonObject>()
                .Where(path => !run.IsLookup || CompositionProjection.String(path["format"]) != "text")
                .Select(path => (JsonNode?)path.DeepClone()).ToArray()),
            ["notes"] = brief["notes"]?.DeepClone() ?? new JsonArray(),
        };
        if (run.IsLookup)
        {
            answer["result"] = CompositionProjection.Facts([run], model: true)[run.Label]!.DeepClone();
        }
        return answer;
    }

    internal static string Fence(string text, string source) =>
        "<<<UNTRUSTED source=" + source + ">>>\n" + text
            .Replace("<<<", "‹‹‹", StringComparison.Ordinal).Replace(">>>", "›››", StringComparison.Ordinal) +
        "\n<<<END UNTRUSTED>>>";

    private static JsonArray Strings(IEnumerable<string> values) =>
        new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());
}
