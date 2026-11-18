using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.DataMap;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed partial class CapabilityData(IGoldDataQueryPort query, IGoldReadPort gold,
    IWriterEntitlement writers, CapabilityOptions options, TimeProvider clock)
{
    private const string GroupSize = "_capability_group_size";
    private static readonly string[][] DistinctHeader = [["Value", "Rows"]];

    internal async Task<CapabilityResult> InvokeAsync(string tool, JsonObject args, ApiPrincipal principal, CancellationToken cancellationToken)
    {
        var writer = principal.EffectiveOid is { Length: > 0 } oid &&
            await writers.IsWriterAsync(oid, cancellationToken).ConfigureAwait(false);
        if (tool == "data_catalog")
        {
            return Catalog(args, principal, writer);
        }
        var spec = Specification(args, tool == "data_distinct_values");
        var dataset = query.Catalog().FirstOrDefault(entry => entry.Name == spec.Dataset)
            ?? throw new CapabilityException(503, "data_source_disabled", "That dataset is not available in this environment.");
        if (!dataset.HasMethod)
        {
            spec = spec with { Method = null };
        }
        if (spec.Select.Count == 0 && spec.Measures.Count == 0)
        {
            throw new CapabilityException(422, "empty_query", "Select at least one column or measure.");
        }
        if (tool == "data_distinct_values")
        {
            return Distinct(args, spec, dataset, writer, cancellationToken);
        }
        var raw = IsEmployeeResult(dataset, spec);
        if (raw && !writer && !(principal.IsAgent && principal.ActingFor?.IsFirstParty == true))
        {
            throw new CapabilityException(403, "employee_level_not_allowed",
                "Employee-level rows are available only in an entitled first-party channel or to a writer. Ask for an aggregate instead.");
        }
        var enforceGroups = dataset.EmployeeLevel && spec.Measures.Count != 0 && !writer;
        var running = enforceGroups ? WithGroupSize(spec, dataset) : spec;
        var result = query.Run(running, cancellationToken);
        var suppressed = 0;
        if (enforceGroups)
        {
            (result, suppressed) = Suppress(result, spec.GroupBy.Count != 0, options.MinimumGroupSize);
        }
        return RenderQuery(spec, dataset, result, suppressed, enforceGroups, writer);
    }

    private static GoldQuerySpec Specification(JsonObject args, bool distinct)
    {
        var select = distinct ? new[] { args["column"]!.GetValue<string>() } : List(args["select"]);
        var measures = distinct ? new[] { new GoldQueryMeasure("*", "count", "row_count") } :
            (args["measures"] as JsonArray ?? []).Select(node => new GoldQueryMeasure(node!["column"]!.GetValue<string>(),
                node["agg"]!.GetValue<string>(), node["as"]?.GetValue<string>())).ToArray();
        return new GoldQuerySpec
        {
            Dataset = args["dataset"]!.GetValue<string>(),
            ClientId = CapabilityJson.Integer(args["client_id"]!),
            TaxYears = Years(args["tax_years"]),
            Select = select,
            Measures = measures,
            Filters = (args["filters"] as JsonArray ?? []).Select(node => new GoldQueryFilter(node!["column"]!.GetValue<string>(),
                node["op"]!.GetValue<string>(), Plain(node["value"]))).ToArray(),
            GroupBy = distinct ? select : args.ContainsKey("group_by") ? List(args["group_by"]) : measures.Length == 0 ? [] : select,
            OrderBy = (args["order_by"] as JsonArray ?? []).Select(node => new GoldQueryOrder(node!["column"]!.GetValue<string>(),
                node["direction"]?.GetValue<string>() ?? "asc")).ToArray(),
            Limit = args["limit"] is { } limit ? CapabilityJson.SmallInteger(limit) : (distinct ? 50 : 100),
            Method = args["method"]?.GetValue<string>(),
        };
    }

    private static int[] Years(JsonNode? value)
    {
        if (value is JsonArray years)
        {
            return years.Select(year => CapabilityJson.SmallInteger(year!)).Distinct().Order().ToArray();
        }
        if (value is not JsonObject range)
        {
            return [];
        }
        var first = CapabilityJson.SmallInteger(range["from"]!);
        var last = CapabilityJson.SmallInteger(range["to"]!);
        if (first > last || (long)last - first >= 12)
        {
            throw new CapabilityException(422, "malformed_spec", "A year range must contain between one and twelve ordered years.");
        }
        return Enumerable.Range(first, last - first + 1).ToArray();
    }

    private static string[] List(JsonNode? array) => (array as JsonArray ?? []).Select(value => value!.GetValue<string>()).ToArray();

    private static object? Plain(JsonNode? node) => node switch
    {
        null => null,
        JsonArray array => array.Select(Plain).ToArray(),
        _ when node.GetValueKind() == JsonValueKind.String => node.GetValue<string>(),
        _ when node.GetValueKind() is JsonValueKind.True or JsonValueKind.False => node.GetValue<bool>(),
        _ when node.GetValueKind() == JsonValueKind.Number => CapabilityJson.Number(node),
        _ => throw CapabilityException.Invalid("Filter value must be a scalar or list."),
    };

    private static bool IsEmployeeResult(GoldQueryDataset dataset, GoldQuerySpec spec) =>
        spec.Select.Any(name => dataset.Columns.Any(column => column.Name == name && column.Sensitivity == "employee_level")) ||
        dataset.EmployeeLevel && spec.Measures.Count == 0;

    private static GoldQuerySpec WithGroupSize(GoldQuerySpec spec, GoldQueryDataset dataset)
    {
        // Tokens identify a person only within a tax year. Never count tokens across years as people.
        if (spec.Measures.Count >= 6 || spec.Select.Contains(GroupSize, StringComparer.Ordinal) ||
            spec.Measures.Any(measure => measure.Alias == GroupSize) ||
            spec.TaxYears.Count != 1 && !spec.GroupBy.Contains("tax_year", StringComparer.Ordinal) ||
            !dataset.Columns.Any(column => column.Name == "record_token" && column.Aggregations.Contains("count_distinct", StringComparer.Ordinal)))
        {
            throw CapabilityException.Missing("W1 Persistence", "IGoldDataQueryPort: atomic hidden distinct-person count for cross-year or six-measure aggregate suppression");
        }
        return spec with { Measures = spec.Measures.Append(new GoldQueryMeasure("record_token", "count_distinct", GroupSize)).ToArray() };
    }

    private static (GoldQueryResult Result, int Suppressed) Suppress(GoldQueryResult result, bool grouped, int minimum)
    {
        var sizes = result.Rows.Select(row => Convert.ToInt64(row[GroupSize], CultureInfo.InvariantCulture)).ToArray();
        if (grouped && sizes.Length > 0 && sizes.All(size => size == 1))
        {
            throw new CapabilityException(422, "groups_are_individuals", "Every group holds one person. Group by a coarser category instead.");
        }
        var kept = result.Rows.Where((_, index) => sizes[index] == 0 || sizes[index] >= minimum)
            .Select(row => (IReadOnlyDictionary<string, object?>)row.Where(pair => pair.Key != GroupSize)
                .ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal)).ToArray();
        return (new GoldQueryResult(result.Columns.Where(name => name != GroupSize).ToArray(), kept, result.Truncated, result.EmployeeLevel),
            result.Rows.Count - kept.Length);
    }

    private CapabilityResult Distinct(JsonObject args, GoldQuerySpec spec, GoldQueryDataset dataset, bool writer, CancellationToken cancellationToken)
    {
        var column = args["column"]!.GetValue<string>();
        var category = dataset.Columns.FirstOrDefault(entry => entry.Name == column)
            ?? throw ColumnRefusal("unknown_column", "No such column in that dataset; read the catalogue for its names.");
        if (category.Sensitivity == "blocked")
        {
            throw ColumnRefusal("blocked_column", "That column can never be listed.");
        }
        if (category.Sensitivity != "public_aggregate" || category.Role is not ("dimension" or "flag"))
        {
            throw ColumnRefusal("column_not_listable", "Only public category columns may be listed.");
        }
        if (dataset.EmployeeLevel && !writer)
        {
            throw CapabilityException.Missing("W1 Persistence", "IGoldDataQueryPort.DistinctValues: distinct-person small-group suppression before merging method counts");
        }
        var result = query.DistinctValues(spec.ClientId, spec.Dataset, column, spec.TaxYears, spec.Limit, cancellationToken);
        var facts = new JsonObject
        {
            ["dataset"] = spec.Dataset,
            ["column"] = column,
            ["client_id"] = spec.ClientId,
            ["tax_years"] = JsonSerializer.SerializeToNode(spec.TaxYears),
            ["value_count"] = result.Rows.Count,
            ["truncated"] = result.Truncated,
            ["row_limit"] = spec.Limit,
            ["values"] = JsonSerializer.SerializeToNode(result.Rows),
            ["source"] = Source(spec.Dataset),
            ["notes"] = new JsonArray(),
        };
        var rows = result.Rows.Select(row => new[] { Cell(row["value"], category), Cell(row["row_count"], null) });
        var blocks = new JsonArray(Block("heading", $"Distinct values · {spec.Dataset}.{column}"),
            result.Rows.Count != 0 ? Block("table", rows: DistinctHeader.Concat(rows)) :
                Block("paragraph", "No values: the client holds no rows for that selection."));
        if (result.Truncated)
        {
            blocks.Add(Block("callout", "The list was cut at the limit; there are more values. Filter, or raise the limit up to 100."));
        }
        blocks.Add(Block("paragraph", Source(spec.Dataset) + "."));
        return new CapabilityResult("data_distinct_values", facts)
        {
            Blocks = blocks,
            Provenance = CapabilityDirectReads.RunEvidence(
                JsonSerializer.SerializeToNode(gold.LatestRun(spec.ClientId)), Source(spec.Dataset)),
        };
    }

    private static CapabilityException ColumnRefusal(string code, string message) =>
        new(422, code, message, extra: new JsonObject { ["field"] = "column" });

    private static string Source(string dataset) => $"Source: warehouse {(dataset == "run_manifest" ? PhysicalNames.Active.Map.OpsSchema : PhysicalNames.Active.Map.GoldSchema)}.{dataset}";
}
