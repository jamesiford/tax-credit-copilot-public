using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Sources.Mapping;

/// <summary>One logical field's physical mapping; semantics cannot be changed by adding unknown fields.</summary>
public sealed record SourceField(string Column, string Type, bool Required, bool Engine);

/// <summary>A closed logical table and its configured physical name.</summary>
public sealed record SourceTable(string Logical, string Physical, string? TenantField,
    bool Optional, IReadOnlyDictionary<string, SourceField> Fields);

/// <summary>Discovered spelling and missing metadata, so optional absence and casing changes remain visible.</summary>
public sealed record ColumnResolution(IReadOnlyDictionary<string, string> Found,
    IReadOnlyList<string> MissingRequired, IReadOnlyList<string> MissingOptional,
    IReadOnlyList<string> CaseDifferences, IReadOnlyList<string> Extra);

/// <summary>Validated immutable mapping, built from the committed Python mapping with an optional configuration patch.</summary>
public sealed partial class SourceMapping
{
    private static readonly HashSet<string> Types = ["int64", "int32", "string", "bool", "double",
        "date32", "timestamp[us]", "decimal128(18, 2)"];

    private SourceMapping(JsonObject root)
    {
        if (root["version"]?.GetValue<int>() != 1)
        {
            throw new ArgumentException("Unsupported source mapping version.");
        }
        CaseInsensitive = root["case_insensitive_columns"]?.GetValue<bool>() ?? true;
        WorksiteMode = root["transforms"]?["worksite_location"]?.GetValue<string>() ?? "worksite_then_location";
        NullPayDateMode = root["transforms"]?["null_pay_date"]?.GetValue<string>() ?? "period_end";
        if (WorksiteMode is not ("worksite_then_location" or "location_only" or "worksite_only")
            || NullPayDateMode is not ("period_end" or "exclude"))
        {
            throw new ArgumentException("Unknown source transform.");
        }
        var prefix = root["naming"]?["table_prefix"]?.GetValue<string>() ?? "";
        var casing = root["naming"]?["table_case"]?.GetValue<string>() ?? "as_is";
        if (casing is not ("as_is" or "lower" or "upper"))
        {
            throw new ArgumentException("Unknown table casing.");
        }
        Tables = ParseTables(root["tables"]!.AsObject(), prefix, casing);
    }

    /// <summary>All supported logical entities.</summary>
    public IReadOnlyDictionary<string, SourceTable> Tables { get; }
    /// <summary>Whether actual column spelling may differ only by case.</summary>
    public bool CaseInsensitive { get; }
    /// <summary>The selected named worksite transform.</summary>
    public string WorksiteMode { get; }
    /// <summary>The selected named null-pay-date transform.</summary>
    public string NullPayDateMode { get; }

    /// <summary>Loads the existing committed mapping; a patch can rename known fields, not invent semantics.</summary>
    public static SourceMapping Load(string? patchJson = null)
    {
        using var stream = typeof(SourceMapping).Assembly.GetManifestResourceStream("Sources.DefaultMapping.json")!;
        var root = JsonNode.Parse(stream)!.AsObject();
        if (patchJson is not null)
        {
            ApplyPatch(root, JsonNode.Parse(patchJson)!.AsObject());
        }
        return new SourceMapping(root);
    }

    /// <summary>Loads the mapping from the data map's Lakehouse section; names and columns come only from that file.</summary>
    public static SourceMapping Load(Domain.DataMap.DataMap map) => new((JsonObject)map.Lakehouse.DeepClone());

    /// <summary>Quotes identifiers after validation; no values are interpolated.</summary>
    public static string Quote(string identifier) => "[" + identifier.Replace("]", "]]", StringComparison.Ordinal) + "]";

    /// <summary>Rejects SQL/path metacharacters before any transport is called.</summary>
    public static void ValidateIdentifier(string identifier)
    {
        if (!Identifier().IsMatch(identifier))
        {
            throw new ArgumentException("Source identifiers must be plain bounded identifiers.");
        }
    }

    /// <summary>Exact spelling wins, then the first case-insensitive match, as in the Python reader.</summary>
    public ColumnResolution Resolve(string logical, IReadOnlyList<string> actual)
    {
        var table = Tables[logical];
        var found = new Dictionary<string, string>(StringComparer.Ordinal);
        var required = new List<string>();
        var optional = new List<string>();
        var cased = new List<string>();
        foreach (var (name, field) in table.Fields)
        {
            var column = actual.FirstOrDefault(c => c == field.Column)
                ?? (CaseInsensitive ? actual.FirstOrDefault(c => string.Equals(c, field.Column, StringComparison.OrdinalIgnoreCase)) : null);
            if (column is null)
            {
                (field.Required ? required : optional).Add(name);
            }
            else
            {
                found.Add(name, column);
                if (column != field.Column) { cased.Add(name); }
            }
        }
        return new ColumnResolution(new ReadOnlyDictionary<string, string>(found), required, optional, cased,
            actual.Where(c => !found.Values.Contains(c, StringComparer.Ordinal)).Order(StringComparer.Ordinal).ToArray());
    }

    [GeneratedRegex("^[A-Za-z0-9_][A-Za-z0-9_\\-]{0,127}$", RegexOptions.CultureInvariant)]
    private static partial Regex Identifier();
}
