using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Json.Schema;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Infrastructure.Rules;

/// <summary>
/// Turns the library's flat result list into <see cref="SchemaFinding"/>s, closing the structural gaps to Python's <c>iter_errors</c> that can be closed
/// exactly (see <see cref="JsonSchemaPackValidator"/>). Nothing here rewrites a library message except for a <c>oneOf</c> that the library reports
/// without one.
/// </summary>
internal static partial class SchemaResultReader
{
    private sealed record Node(string EvaluationPath, string InstancePath, bool Valid, IReadOnlyDictionary<string, string>? Errors, string SchemaFragment);

    private sealed record OneOfGroup(string Prefix, string InstancePath, int Valid, int Branches);

    internal static IReadOnlyList<SchemaFinding> Read(EvaluationResults root, JsonElement instance, JsonNode schema)
    {
        var nodes = new List<Node>();
        Flatten(root, nodes);
        var groups = OneOfGroups(nodes);
        var findings = new List<SchemaFinding>();
        var reported = new HashSet<OneOfGroup>();
        var dropped = 0;
        foreach (var node in nodes)
        {
            var group = GroupOf(node, groups);
            if (group is not null)
            {
                // A passing oneOf discards its failed branches; a failing one is one finding at the object, reported where its first branch was.
                if (group.Valid != 1 && reported.Add(group))
                {
                    findings.Add(new SchemaFinding(PathOf(group.InstancePath, instance), OneOfMessage(group), "oneOf"));
                }

                continue;
            }

            if (node.Valid || node.Errors is not { Count: > 0 })
            {
                continue;
            }

            var location = node.EvaluationPath.Contains("/propertyNames", StringComparison.Ordinal) ? WithoutLastSegment(node.InstancePath) : node.InstancePath;
            foreach (var error in node.Errors)
            {
                if (error.Key == "minLength" && CountsEnough(node, instance, schema, location))
                {
                    dropped++;
                    continue;
                }

                // jsonschema yields a false-schema error without the path of the property it rejected (descend() prepends the path only to errors it passes up).
                var at = error.Key.Length == 0 ? WithoutLastSegment(location) : location;
                findings.Add(new SchemaFinding(PathOf(at, instance), error.Value, error.Key.Length == 0 ? null : error.Key));
            }
        }

        // The decision must never depend on the findings being readable: an invalid document is reported even when no violation could be attributed.
        return findings.Count == 0 && dropped == 0 && !root.IsValid
            ? [new SchemaFinding([], "The document does not match the schema (no violation was reported by the validator).", null)]
            : findings;
    }

    private static void Flatten(EvaluationResults result, List<Node> into)
    {
        into.Add(new Node(result.EvaluationPath.ToString(), result.InstanceLocation.ToString(), result.IsValid, result.Errors, result.SchemaLocation.Fragment));
        foreach (var detail in result.Details ?? [])
        {
            Flatten(detail, into);
        }
    }

    // The library measures a string in text elements (a base letter plus its accent is one); Python measures code points. Text elements never outnumber code
    // points, so the library can only be too strict: its minLength finding is dropped when the code points reach the minimum.
    private static bool CountsEnough(Node node, JsonElement instance, JsonNode schema, string location)
    {
        var current = (JsonNode?)schema;
        foreach (var raw in Uri.UnescapeDataString(node.SchemaFragment).TrimStart('#').Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            var segment = raw.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal);
            current = current is JsonObject o ? o[segment] : null;
        }

        var value = PathOf(location, instance).Aggregate(instance, (e, s) => s is long i ? e[(int)i] : e.GetProperty((string)s));
        return current?["minLength"] is JsonNode minimum && value.ValueKind == JsonValueKind.String && PyStr.Length(value.GetString()!) >= minimum.GetValue<long>();
    }

    private static List<OneOfGroup> OneOfGroups(List<Node> nodes)
    {
        var branches = nodes.Select(n => (Node: n, Match: BranchPattern().Match(n.EvaluationPath))).Where(x => x.Match.Success).ToList();
        return branches
            .GroupBy(b => (Prefix: b.Match.Groups["prefix"].Value, b.Node.InstancePath))
            .Select(g => new OneOfGroup(g.Key.Prefix, g.Key.InstancePath, g.Count(b => b.Node.Valid), g.Count()))
            .ToList();
    }

    private static OneOfGroup? GroupOf(Node node, List<OneOfGroup> groups) => groups.FirstOrDefault(g =>
        node.EvaluationPath.StartsWith(g.Prefix + "/oneOf/", StringComparison.Ordinal)
        && (node.InstancePath == g.InstancePath || node.InstancePath.StartsWith(g.InstancePath + "/", StringComparison.Ordinal)));

    // The library says nothing when several branches match, and Python's wording quotes the whole value; these sentences are the adapter's.
    private static string OneOfMessage(OneOfGroup g) => g.Valid == 0
        ? "The value does not match any of the schemas of the oneOf."
        : $"The value matches {g.Valid} of the {g.Branches} schemas of the oneOf; it must match exactly one.";

    private static string WithoutLastSegment(string pointer)
    {
        var cut = pointer.LastIndexOf('/');
        return cut <= 0 ? string.Empty : pointer[..cut];
    }

    // A pointer segment is an index in an array and a key in an object; Python's path says which, and "0" the key is not 0 the index.
    private static List<object> PathOf(string pointer, JsonElement instance)
    {
        var path = new List<object>();
        if (pointer.Length == 0)
        {
            return path;
        }

        var current = instance;
        foreach (var raw in pointer[1..].Split('/'))
        {
            var segment = raw.Replace("~1", "/", StringComparison.Ordinal).Replace("~0", "~", StringComparison.Ordinal);
            if (current.ValueKind == JsonValueKind.Array)
            {
                var index = long.Parse(segment, System.Globalization.CultureInfo.InvariantCulture);
                path.Add(index);
                current = current[(int)index];
            }
            else
            {
                path.Add(segment);
                current = current.GetProperty(segment);
            }
        }

        return path;
    }

    [GeneratedRegex(@"^(?<prefix>.*)/oneOf/\d+$", RegexOptions.CultureInvariant)]
    private static partial Regex BranchPattern();
}
