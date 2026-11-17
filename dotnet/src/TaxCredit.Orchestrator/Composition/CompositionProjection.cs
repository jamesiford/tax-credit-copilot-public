using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Orchestrator.Composition;

internal static partial class CompositionProjection
{
    internal const int ModelRowLimit = 50;

    internal static CompositionRun Snapshot(CompositionRun run) => run with
    {
        Arguments = (JsonObject)run.Arguments.DeepClone(),
        Result = run.Result with
        {
            Facts = (JsonObject)run.Result.Facts.DeepClone(),
            Blocks = (JsonArray)run.Result.Blocks.DeepClone(),
            Provenance = (JsonObject)run.Result.Provenance.DeepClone(),
            Warnings = run.Result.Warnings.ToArray(),
            UserOnlyFacts = run.Result.UserOnlyFacts.ToArray(),
        },
    };

    internal static JsonObject Facts(IReadOnlyList<CompositionRun> runs, bool model)
    {
        var result = new JsonObject();
        foreach (var run in runs)
        {
            if (!LabelPattern().IsMatch(run.Label) || result.ContainsKey(run.Label))
            {
                throw new ArgumentException("Composition labels must be unique path components.", nameof(runs));
            }
            if (run.Result.UserOnlyFacts.Any(key => !run.Result.Facts.ContainsKey(key)))
            {
                throw new InvalidOperationException("invalid_person_lane_declaration");
            }
            var facts = model ? run.Result.ModelFacts() : (JsonObject)run.Result.Facts.DeepClone();
            Project(facts, model);
            RemoveSecretCopies(facts, Secrets([run]));
            result[run.Label] = facts;
        }
        return result;
    }

    private static void Project(JsonNode? node, bool model, int depth = 0)
    {
        if (depth > 64)
        {
            throw new InvalidOperationException("capability_evidence_too_deep");
        }
        if (node is JsonObject value)
        {
            foreach (var key in value.Select(pair => pair.Key).ToArray())
            {
                if (key.Contains('.'))
                {
                    throw new InvalidOperationException("ambiguous_fact_path");
                }
                if (IsSecret(key) || model && key is "employee_id" or "employeeId" or "record_token")
                {
                    value.Remove(key);
                }
            }
            if (model && value.TryGetPropertyValue("audience", out var audience) && String(audience) != "both")
            {
                value.Remove("rows");
            }
            foreach (var (_, child) in value)
            {
                Project(child, model, depth + 1);
            }
            if (model && value["rows"] is JsonArray rows)
            {
                while (rows.Count > ModelRowLimit)
                {
                    rows.RemoveAt(rows.Count - 1);
                }
            }
        }
        else if (node is JsonArray array)
        {
            foreach (var child in array)
            {
                Project(child, model, depth + 1);
            }
        }
    }

    internal static bool IsSecret(string key) =>
        key is "confirmation" or "confirmation_token" or "confirmationToken";

    internal static IReadOnlyList<string> Secrets(IReadOnlyList<CompositionRun> runs)
    {
        var secrets = new List<string>();
        static void Walk(JsonNode? node, bool secret, List<string> found)
        {
            if (node is JsonObject value)
            {
                foreach (var (key, child) in value)
                {
                    Walk(child, secret || IsSecret(key), found);
                }
            }
            else if (node is JsonArray array)
            {
                foreach (var child in array)
                {
                    Walk(child, secret, found);
                }
            }
            else if (secret && String(node) is { Length: > 0 } text)
            {
                found.Add(text);
            }
        }
        foreach (var run in runs)
        {
            Walk(run.Result.Facts, false, secrets);
        }
        return secrets.Distinct(StringComparer.Ordinal).ToArray();
    }

    private static void RemoveSecretCopies(JsonNode? node, IReadOnlyList<string> secrets)
    {
        if (node is JsonObject value)
        {
            foreach (var (key, child) in value.ToArray())
            {
                if (String(child) is { } text && secrets.Any(secret => text.Contains(secret, StringComparison.Ordinal)))
                {
                    value.Remove(key);
                }
                else
                {
                    RemoveSecretCopies(child, secrets);
                }
            }
        }
        else if (node is JsonArray array)
        {
            for (var index = 0; index < array.Count; index++)
            {
                if (String(array[index]) is { } text && secrets.Any(secret => text.Contains(secret, StringComparison.Ordinal)))
                {
                    array[index] = null;
                }
                else
                {
                    RemoveSecretCopies(array[index], secrets);
                }
            }
        }
    }

    internal static bool HasUserLane(CompositionRun run) => run.Result.UserOnlyFacts.Count != 0 ||
        run.Result.Facts.TryGetPropertyValue("audience", out var audience) && String(audience) != "both" ||
        run.Result.Blocks.OfType<JsonObject>().Any(IsUserBlock);

    internal static bool IsUserBlock(JsonObject block) =>
        block.TryGetPropertyValue("audience", out var audience) && String(audience) != "both";

    internal static string? String(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;

    internal static FactIndex Index(JsonObject facts)
    {
        try
        {
            return FactIndex.FromFacts(JsonSerializer.SerializeToElement(facts));
        }
        catch (JsonException)
        {
            throw new InvalidOperationException("invalid_capability_evidence");
        }
    }

    internal static bool CanonicalPath(string path) => path.Split('.').All(part => ComponentPattern().IsMatch(part));

    internal static AllowedContext Context(string question, IReadOnlyList<CompositionRun> runs) =>
        AllowedContext.Build([question],
            runs.SelectMany(run => new[] { Integer(run.Arguments["tax_year"]), Integer(run.Arguments["year"]) })
                .OfType<int>().Distinct(),
            runs.Select(run => Integer(run.Arguments["client_id"])).OfType<int>().Select(value => (object)value).Distinct());

    private static int? Integer(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue<int>(out var number) ? number : null;

    internal static IReadOnlyList<string> HiddenText(FactIndex full, FactIndex model)
    {
        var visible = model.Leaves.Values.Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString()!).ToHashSet(StringComparer.OrdinalIgnoreCase);
        return full.Leaves.Where(pair => !model.Leaves.ContainsKey(pair.Key) &&
                pair.Value.ValueKind == JsonValueKind.String)
            .Select(pair => pair.Value.GetString()!)
            .Where(text => text.Length >= 4 && !visible.Contains(text) &&
                !FactPlaceholders.IsNumeric(text))
            .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    internal static bool ContainsHiddenText(string text, IEnumerable<string> hidden) =>
        hidden.Any(value => text.Contains(value, StringComparison.OrdinalIgnoreCase));

    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_]*$")]
    private static partial Regex LabelPattern();

    [GeneratedRegex(@"^[A-Za-z0-9_-]+$")]
    private static partial Regex ComponentPattern();
}
