using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Persistence;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed partial class CapabilityData
{
    private CapabilityResult RenderQuery(GoldQuerySpec spec, GoldQueryDataset dataset, GoldQueryResult result,
        int suppressed, bool enforced, bool writer)
    {
        var source = Source(spec.Dataset);
        var run = JsonSerializer.SerializeToNode(gold.LatestRun(spec.ClientId));
        var asOf = run?["completed_at"]?.ToString() ?? run?["produced_at"]?.ToString() ??
            clock.GetUtcNow().ToString("yyyy-MM-dd'T'HH:mm:sszzz", CultureInfo.InvariantCulture);
        var notes = new List<string>();
        if (result.Truncated)
        {
            notes.Add($"The result was cut at {spec.Limit} rows; narrow the question or use an aggregate.");
        }
        if (suppressed != 0)
        {
            notes.Add($"{suppressed} group(s) with fewer than {options.MinimumGroupSize} people were left out of this result so that no individual can be identified. The groups shown are exact and complete.");
        }
        var columns = ResultColumns(spec, dataset, result.Columns);
        var facts = new JsonObject
        {
            ["dataset"] = spec.Dataset,
            ["audience"] = result.EmployeeLevel ? "user" : "both",
            ["client_id"] = spec.ClientId,
            ["tax_years"] = JsonSerializer.SerializeToNode(spec.TaxYears),
            ["method"] = dataset.HasMethod ? spec.Method ?? "both" : null,
            ["row_count"] = result.Rows.Count,
            ["displayed_rows"] = Math.Min(result.Rows.Count, 50),
            ["row_limit"] = spec.Limit,
            ["truncated"] = result.Truncated,
            ["as_of"] = asOf,
            ["source"] = source,
            ["columns"] = new JsonArray(columns.Select(column => (JsonNode)new JsonObject
            {
                ["name"] = column.Name,
                ["kind"] = column.Role,
                ["unit"] = column.Unit,
                ["person_level"] = column.Sensitivity == "employee_level",
            }).ToArray()),
            ["rows"] = JsonSerializer.SerializeToNode(result.Rows),
            ["select"] = JsonSerializer.SerializeToNode(spec.Select),
            ["group_by"] = JsonSerializer.SerializeToNode(spec.GroupBy),
            ["measures"] = new JsonArray(spec.Measures.Select(measure => (JsonNode)new JsonObject
            {
                ["column"] = measure.Column,
                ["agg"] = measure.Aggregation,
                ["as"] = Label(measure),
            }).ToArray()),
            ["filters"] = Filters(spec, dataset),
            ["notes"] = Strings(notes),
        };
        if (dataset.EmployeeLevel && spec.Measures.Count != 0)
        {
            facts["small_groups"] = new JsonObject
            {
                ["min_group_size"] = options.MinimumGroupSize,
                ["applied"] = enforced,
                ["suppressed_groups"] = suppressed,
                ["exempt"] = writer ? "writer" : null,
                ["basis"] = "distinct people in the group",
            };
        }
        var blocks = new JsonArray(Block("heading", $"Query result · {spec.Dataset}"));
        blocks.Add(result.Rows.Count == 0 ? Block("paragraph", "No rows matched. That is a result about the data, not an error.") :
            Block("table", rows: new[] { columns.Select(column => column.Unit is null ? column.Name : $"{column.Name} ({column.Unit})") }
                .Concat(result.Rows.Take(50).Select(row => columns.Select(column => Cell(row[column.Name], column)))),
                audience: result.EmployeeLevel ? "user" : "both"));
        if (result.Rows.Count > 50)
        {
            blocks.Add(Block("callout", $"Showing the first 50 of {result.Rows.Count} rows here. Narrow the question, or ask for an aggregate, to see the rest."));
        }
        if (result.EmployeeLevel)
        {
            blocks.Add(Block("callout", "These rows describe individual employees. They are shown to you and are not given to any AI model."));
        }
        foreach (var note in notes)
        {
            blocks.Add(Block("callout", note));
        }
        blocks.Add(Block("paragraph", $"{source}. As of {CapabilityFormat.Render(JsonValue.Create(asOf), "date")}."));
        return new CapabilityResult("data_query", facts)
        {
            Blocks = blocks,
            Provenance = CapabilityDirectReads.RunEvidence(run, source),
            Warnings = result.EmployeeLevel ? [.. notes, "Sensitive: this result lists individual employees."] : notes,
            UserOnlyFacts = result.EmployeeLevel ? ["rows"] : [],
        };
    }

    private static GoldQueryColumn[] ResultColumns(GoldQuerySpec spec, GoldQueryDataset dataset, IReadOnlyList<string> labels) =>
        labels.Select(name => dataset.Columns.FirstOrDefault(column => column.Name == name) ??
            MeasureColumn(name, spec, dataset)).ToArray();

    private static GoldQueryColumn MeasureColumn(string name, GoldQuerySpec spec, GoldQueryDataset dataset)
    {
        var measure = spec.Measures.First(item => Label(item) == name);
        var source = dataset.Columns.FirstOrDefault(column => column.Name == measure.Column);
        var count = measure.Aggregation is "count" or "count_distinct" || source?.Type == "bool";
        return new GoldQueryColumn(name, count ? "int" : source?.Type ?? "decimal", "measure", "public_aggregate", [], [],
            count ? null : source?.Unit);
    }

    private static JsonArray Filters(GoldQuerySpec spec, GoldQueryDataset dataset) => new(spec.Filters.Select(filter => (JsonNode)new JsonObject
    {
        ["column"] = filter.Column,
        ["op"] = filter.Operator,
        ["value"] = dataset.Columns.Any(column => column.Name == filter.Column && column.Sensitivity == "public_aggregate")
            ? JsonSerializer.SerializeToNode(filter.Value) : JsonValue.Create("<redacted>"),
    }).ToArray());

    private static string Label(GoldQueryMeasure measure) => measure.Alias ??
        (measure.Column == "*" ? "row_count" : measure.Aggregation + "_" + measure.Column);

    private static string Cell(object? value, GoldQueryColumn? column)
    {
        if (value is null)
        {
            return "—";
        }
        if (value is bool boolean)
        {
            return boolean ? "yes" : "no";
        }
        var node = JsonSerializer.SerializeToNode(value);
        var numeric = node?.GetValueKind() == JsonValueKind.Number;
        if (column?.Unit != "USD" && !numeric)
        {
            return node?.ToString() ?? "—";
        }
        var format = column?.Unit == "USD" ? "money" : column?.Name is "tax_year" or "year" or "base_tax_year" ||
            column?.Name.EndsWith("_tax_year", StringComparison.Ordinal) == true ? "year" : "number";
        return CapabilityFormat.Render(node, format);
    }
}
