using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// Validates rule packs: JSON Schema for shape, then the semantic rules a schema cannot say (Python <c>tools/pack_validation.py</c>). [ADR-013, ADR-005]
/// A pack that passes is <em>valid</em>, not <em>verified</em>: the <c>_prototype_verify</c> flags it carries are reported.
/// </summary>
/// <remarks>
/// The schema step is the <see cref="IJsonSchemaValidator"/> port (a library and a file read, neither of which the Domain may hold); everything else, including
/// the order in which findings are added, is Python's. The rules folder is read through <see cref="IRulePackSource"/>, and a report names a file as
/// <c>&lt;rules folder&gt;/&lt;relative path&gt;</c> (Python prints the operating-system path).
/// </remarks>
public sealed partial class PackValidator
{
    private readonly IRulePackSource _source;
    private readonly IJsonSchemaValidator _schema;
    private readonly RuleLibrary _library;

    /// <summary>Initialises the validator.</summary>
    /// <param name="source">The rules folder whose packs <see cref="ValidatePack"/> and <see cref="ValidateAll"/> read.</param>
    /// <param name="schema">The JSON Schema step.</param>
    /// <param name="library">The library that reads the registry for <see cref="ValidateAll"/>; <c>null</c> builds one over <paramref name="source"/>.</param>
    public PackValidator(IRulePackSource source, IJsonSchemaValidator schema, RuleLibrary? library = null)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(schema);
        _source = source;
        _schema = schema;
        _library = library ?? new RuleLibrary(source);
    }

    /// <summary>Python <c>schema_version()</c>.</summary>
    /// <returns>The schema's <c>schema_version</c>.</returns>
    public int SchemaVersion() => _schema.SchemaVersion;

    /// <summary>
    /// Python <c>validate_document</c>: validates one pack held in memory, as it would be named on disk (<paramref name="name"/>, for example
    /// <c>zz_demo.json</c> or <c>2025.json</c>). The portal validates a draft's documents with this and never writes them to a folder, so a draft and a committed
    /// pack are judged by exactly the same rules.
    /// </summary>
    /// <param name="pack">The document: a JSON tree.</param>
    /// <param name="name">The file name it would have.</param>
    /// <param name="kind"><c>year</c> or <c>base</c> (any other value is judged as a base pack).</param>
    /// <param name="yearsAuthored">Whether the program has authored year packs (a base pack that prices by percentage of wages is then an error, not a warning).</param>
    /// <param name="file">The file as shown; empty shows <paramref name="name"/>.</param>
    /// <returns>The report.</returns>
    /// <exception cref="PyAttributeError">When a block that must be a mapping is another truthy value, as Python raises it.</exception>
    /// <exception cref="PyTypeError">When a block is a number where text or a mapping is read.</exception>
    public PackReport ValidateDocument(object? pack, string name, string kind, bool yearsAuthored = false, string file = "")
    {
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(kind);
        var report = new PackReport(file.Length > 0 ? file : name, kind);
        CheckSchema(pack, kind, report);
        if (pack is PyDict dict)
        {
            PackSemanticChecks.CheckNames(name, dict, kind, report);
            PackSemanticChecks.CheckModels(dict, kind, yearsAuthored, report);
            PackSemanticChecks.CheckThresholds(dict, report);
            PackSemanticChecks.CheckVerifiedClaim(dict, report);
            foreach (var flagged in PackSemanticChecks.Flags(dict))
            {
                report.Add("info", "unverified", "carries _prototype_verify: not verified", flagged);
            }
        }

        return report;
    }

    /// <summary>Python <c>check_schema</c>: structural errors, one per violation, each naming the path inside the pack, sorted by path (stable).</summary>
    private void CheckSchema(object? pack, string kind, PackReport report)
    {
        var findings = PySort.Sorted(_schema.Validate(pack, kind), f => f.Path, PathComparer);
        foreach (var finding in findings)
        {
            report.Add("error", "schema", PyStr.Prefix(finding.Message, 300), string.Join('/', finding.Path.Select(PathSegment)));
        }
    }

    private static string PathSegment(object segment) =>
        segment as string ?? ((long)segment).ToString(System.Globalization.CultureInfo.InvariantCulture);

    /// <summary>Python list ordering over path segments: element by element (integers numerically, text by code point), a prefix first.</summary>
    internal static IComparer<IReadOnlyList<object>> PathComparer { get; } = Comparer<IReadOnlyList<object>>.Create(ComparePaths);

    private static int ComparePaths(IReadOnlyList<object> a, IReadOnlyList<object> b)
    {
        for (var i = 0; i < Math.Min(a.Count, b.Count); i++)
        {
            var c = (a[i], b[i]) switch
            {
                (string x, string y) => PyStr.Compare(x, y),
                (long x, long y) => x.CompareTo(y),
                (long, string) => throw new PyTypeError("'<' not supported between instances of 'int' and 'str'"),
                _ => throw new PyTypeError("'<' not supported between instances of 'str' and 'int'"),
            };
            if (c != 0)
            {
                return c;
            }
        }

        return a.Count.CompareTo(b.Count);
    }
}
