using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Auth;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed partial class CapabilityData
{
    private const string NextStep = "Pass dataset=<name> to see a dataset's columns, then call data_query with those names exactly.";
    private const string CoworkNote = "Over Copilot Cowork, rows that list individual employees are not available unless the user is entitled to make changes; counts, sums and averages over employees are.";
    private static readonly string[][] CatalogColumnHeader = [["Column", "Role", "Unit", "Meaning", "Aggregations", "Filters"]];
    private static readonly string[][] CatalogDatasetHeader = [["Dataset", "One row is", "Source"]];

    private CapabilityResult Catalog(JsonObject args, ApiPrincipal principal, bool writer)
    {
        var requested = args["dataset"]?.GetValue<string>();
        var needle = args["search"]?.GetValue<string>().Trim().ToLowerInvariant();
        var available = query.Catalog().ToDictionary(dataset => dataset.Name, StringComparer.Ordinal);
        var metadata = JsonNode.Parse(CapabilitySemanticMetadata.Json)!.AsArray();
        var asked = metadata.OfType<JsonObject>().Where(dataset => requested is null || dataset["name"]!.GetValue<string>() == requested).ToArray();
        var omitted = asked.Count(dataset => !available.ContainsKey(dataset["name"]!.GetValue<string>()));
        var entries = new JsonArray();
        foreach (var dataset in asked)
        {
            var name = dataset["name"]!.GetValue<string>();
            if (!available.TryGetValue(name, out var portDataset))
            {
                continue;
            }
            var columns = dataset["columns"]!.AsArray().OfType<JsonObject>()
                .Where(column => portDataset.Columns.Any(held => held.Name == column["name"]!.GetValue<string>() && held.Sensitivity != "blocked"))
                .ToArray();
            var matching = columns.Where(column => needle is null || Match(column["name"], needle) || Match(column["description"], needle)).ToArray();
            if (requested is null && needle is not null && matching.Length == 0 &&
                !Match(dataset["name"], needle) && !Match(dataset["description"], needle) && !Match(dataset["grain"], needle))
            {
                continue;
            }
            var entry = new JsonObject(dataset.Where(pair => pair.Key is not ("columns" or "engine_notes" or "joins"))
                .Select(pair => KeyValuePair.Create(pair.Key, pair.Value?.DeepClone())));
            entry["column_count"] = columns.Length;
            if (requested is not null || needle is not null)
            {
                entry["columns"] = new JsonArray((requested is not null ? matching : matching.Take(15)).Select(column => column.DeepClone()).ToArray());
            }
            if (requested is not null)
            {
                entry["engine_notes"] = dataset["engine_notes"]!.DeepClone();
                entry["joins"] = new JsonArray();
            }
            entries.Add(entry);
        }
        var notes = new List<string>();
        if (requested is null)
        {
            notes.Add(NextStep);
        }
        if (needle is not null && entries.Count == 0 && omitted == 0)
        {
            notes.Add("No dataset or column matches that search, so the data has nothing for it. Say so; do not guess a column name. Try a different word, or call with no search to list every dataset.");
        }
        if (omitted != 0)
        {
            notes.Add($"{omitted} dataset(s) are not available in this environment and are not listed.");
        }
        if (!(principal.IsAgent && principal.ActingFor?.IsFirstParty == true) && !writer)
        {
            notes.Add(CoworkNote);
        }
        if (entries.Any(entry => entry!["employee_level"]!.GetValue<bool>()))
        {
            notes.Add($"An aggregate over employee-level data leaves out any group of fewer than {options.MinimumGroupSize} people and says how many it left out; that is the platform's privacy rule, so do not try to get around it with a finer grouping or a narrower filter.");
        }
        var facts = new JsonObject { ["dataset_count"] = entries.Count, ["datasets"] = entries, ["notes"] = Strings(notes) };
        return new CapabilityResult("data_catalog", facts)
        {
            Blocks = CatalogBlocks(entries, notes),
            Provenance = Evidence(source: "semantic model; holds no values from the data"),
        };
    }

    private static bool Match(JsonNode? value, string needle) => value?.GetValue<string>().Contains(needle, StringComparison.OrdinalIgnoreCase) == true;

    private static JsonArray CatalogBlocks(JsonArray entries, IReadOnlyList<string> notes)
    {
        var blocks = new JsonArray(Block("heading", "Queryable data"));
        var detailed = entries.Where(entry => entry!["columns"] is not null).ToArray();
        foreach (var entry in detailed)
        {
            blocks.Add(Block("heading", $"{entry!["name"]!.GetValue<string>()} · {entry["grain"]!.GetValue<string>()}"));
            blocks.Add(Block("table", rows: CatalogColumnHeader
                .Concat(entry["columns"]!.AsArray().Select(column => new[]
                {
                    column!["name"]!.GetValue<string>(),
                    column["role"]!.GetValue<string>() + (column["sensitivity"]!.GetValue<string>() == "employee_level" ? ", employee level" : ""),
                    column["unit"]?.GetValue<string>() ?? "—", column["description"]!.GetValue<string>(),
                    Joined(column["aggregations"]), Joined(column["operators"]),
                }))));
        }
        if (detailed.Length == 0)
        {
            blocks.Add(Block("table", rows: CatalogDatasetHeader.Concat(entries.Select(entry => new[]
            {
                entry!["name"]!.GetValue<string>(), entry["grain"]!.GetValue<string>(), entry["source"]!.GetValue<string>(),
            }))));
        }
        foreach (var note in notes)
        {
            blocks.Add(Block("callout", note));
        }
        return blocks;
    }

    private static string Joined(JsonNode? values) => values is JsonArray { Count: > 0 } array ?
        string.Join(", ", array.Select(value => value!.GetValue<string>())) : "—";
}
