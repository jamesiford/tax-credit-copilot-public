using System.IO.Compression;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>One violation as the schema validators report it: keyword, absolute path (text keys and integer indices) and the validator's own wording.</summary>
internal sealed record SchemaViolation(string? Keyword, IReadOnlyList<object> Path, string Message)
{
    /// <summary>The path with each segment tagged by type, so the key <c>"0"</c> and the index <c>0</c> are different places.</summary>
    public string PathKey => string.Join('/', Path.Select(p => p is long l ? "#" + l : "." + p));

    public string Identity => (Keyword ?? "(false schema)") + " @ " + PathKey;
}

/// <summary>One recorded <c>validate_document</c> call with both validators' raw violations for its document.</summary>
internal sealed record DocCase(PyDict Record, IReadOnlyList<SchemaViolation> Python)
{
    public string Label => (string)Record["label"]!;
}

/// <summary>The comparison of Python's raw violations with the .NET library's for one document, under the rules the platform owner will read in the deviations document.</summary>
internal sealed class SchemaComparison
{
    public SchemaComparison(DocCase source, IReadOnlyList<SchemaViolation> library)
    {
        Source = source;
        Python = Sorted(source.Python);
        Library = Sorted(library);
        PythonKeys = Distinct(Python);
        LibraryKeys = Distinct(Library);
    }

    public DocCase Source { get; }

    public IReadOnlyList<SchemaViolation> Python { get; }

    public IReadOnlyList<SchemaViolation> Library { get; }

    public IReadOnlyList<SchemaViolation> PythonKeys { get; }

    public IReadOnlyList<SchemaViolation> LibraryKeys { get; }

    /// <summary>The hard rule: both validators accept, or both reject.</summary>
    public bool DecisionMatches => Python.Count == 0 == (Library.Count == 0);

    /// <summary>The hard rule: the same distinct (keyword, path) pairs are reported.</summary>
    public bool KeysMatch => new HashSet<string>(PythonKeys.Select(v => v.Identity)).SetEquals(LibraryKeys.Select(v => v.Identity));

    /// <summary>Measured: Python reports one violation per missing name (and per failed branch); the library may report fewer or more.</summary>
    public bool CountMatches => Python.Count == Library.Count;

    /// <summary>Measured: the distinct pairs come in the same sequence after both sides are sorted by path (a tie at one path keeps the validator's own order).</summary>
    public bool OrderMatches => PythonKeys.Select(v => v.Identity).SequenceEqual(LibraryKeys.Select(v => v.Identity));

    // The module sorts by absolute path, stably; a tie therefore keeps the order the validator produced.
    private static List<SchemaViolation> Sorted(IReadOnlyList<SchemaViolation> raw) => PySort.Sorted(raw, v => v.Path, PackValidator.PathComparer);

    private static List<SchemaViolation> Distinct(IReadOnlyList<SchemaViolation> sorted)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        return sorted.Where(v => seen.Add(v.Identity)).ToList();
    }
}

/// <summary>Reads <c>pack_validation.jsonl.gz</c> and builds the validators the replay runs against the real <c>backend/rules</c>.</summary>
internal sealed class PackValidationHarness
{
    public const string File = "pack_validation.jsonl.gz";

    private readonly Dictionary<string, PackValidator> _validators = [];
    private readonly Dictionary<string, OverlayRulePackSource> _sources = [];
    private readonly PyDict _worlds;

    public PackValidationHarness()
    {
        Schema = JsonSchemaPackValidator.FromOptions(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory });
        _worlds = (PyDict)Meta()["worlds"]!;
    }

    public JsonSchemaPackValidator Schema { get; }

    public static PyDict Meta()
    {
        GoldenFiles.AssertOracleStamp(File);
        using var stream = System.IO.File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", File));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        return (PyDict)PyJson.Loads(reader.ReadLine()!)!;
    }

    public static IEnumerable<PyDict> Records(string kind) => ClaimGolden.Calls(File).Where(r => (string)r["k"]! == kind);

    public static IReadOnlyList<SchemaViolation> Violations(object? array) =>
        ((List<object?>)array!).Cast<PyDict>().Select(e => new SchemaViolation((string?)e["keyword"], ((List<object?>)e["path"]!).Cast<object>().ToList(), (string)e["message"]!)).ToList();

    public static IReadOnlyList<SchemaViolation> Violations(IReadOnlyList<SchemaFinding> findings) =>
        findings.Select(f => new SchemaViolation(f.Keyword, f.Path, f.Message)).ToList();

    public OverlayRulePackSource Source(string world)
    {
        if (!_sources.TryGetValue(world, out var source))
        {
            source = new OverlayRulePackSource(world == "shipped" ? EmptyOverlay() : (PyDict)_worlds[world]!);
            _sources[world] = source;
        }

        return source;
    }

    public PackValidator Validator(string world)
    {
        if (!_validators.TryGetValue(world, out var validator))
        {
            var source = Source(world);
            validator = new PackValidator(source, Schema, new RuleLibrary(source));
            _validators[world] = validator;
        }

        return validator;
    }

    /// <summary>The Python record uses <c>&lt;RULES&gt;</c> and forward slashes for the machine's rules folder.</summary>
    public string Normalise(string text, string world) => text.Replace(Source(world).RulesDirectory, "<RULES>", StringComparison.Ordinal).Replace('\\', '/');

    private static PyDict EmptyOverlay() => new PyDict().Add("files", new PyDict()).Add("registry_file", null);

    /// <summary>
    /// The first difference between a recorded report and the port's: the verdict, the kind and file, every SEMANTIC issue exactly and in order, and the schema issues by
    /// path (their wording and number are the measured deviations of the schema library, not of the port).
    /// </summary>
    public static string? CompareReport(PyDict expected, PackReport actual, Func<string, string> normalise)
    {
        if ((string)expected["file"]! != normalise(actual.File) || (string)expected["kind"]! != actual.Kind)
        {
            return $"file/kind: got {normalise(actual.File)} / {actual.Kind}, expected {expected["file"]} / {expected["kind"]}";
        }

        if ((bool)expected["ok"]! != actual.Ok)
        {
            return $"ok: got {actual.Ok}, expected {expected["ok"]}";
        }

        var exp = ((List<object?>)expected["issues"]!).Cast<PyDict>().ToList();
        var expectedSemantic = exp.Where(i => (string)i["code"]! != "schema").Select(Show).ToList();
        var actualSemantic = actual.Issues.Where(i => i.Code != "schema").Select(i => Show(i.Severity, i.Code, i.Path, normalise(i.Message))).ToList();
        if (!expectedSemantic.SequenceEqual(actualSemantic))
        {
            return "semantic issues differ:\n  expected " + string.Join(" | ", expectedSemantic) + "\n  got      " + string.Join(" | ", actualSemantic);
        }

        // Both sides sort by path, so the sequence of distinct paths (consecutive repeats folded: Python reports `required` once per name, the library once) must agree.
        var expectedPaths = Fold(exp.Where(i => (string)i["code"]! == "schema").Select(i => (string)i["path"]!));
        var actualPaths = Fold(actual.Issues.Where(i => i.Code == "schema").Select(i => i.Path));
        if (!expectedPaths.SequenceEqual(actualPaths))
        {
            return $"schema issue paths differ: expected [{string.Join(", ", expectedPaths)}] got [{string.Join(", ", actualPaths)}]";
        }

        var firstOther = actual.Issues.ToList().FindIndex(i => i.Code != "schema");
        return firstOther >= 0 && actual.Issues.Skip(firstOther).Any(i => i.Code == "schema") ? "a schema issue follows a semantic one" : null;
    }

    private static List<string> Fold(IEnumerable<string> paths)
    {
        var folded = new List<string>();
        foreach (var path in paths)
        {
            if (folded.Count == 0 || folded[^1] != path)
            {
                folded.Add(path);
            }
        }

        return folded;
    }

    private static string Show(PyDict i) => Show((string)i["severity"]!, (string)i["code"]!, (string)i["path"]!, (string)i["message"]!);

    private static string Show(string severity, string code, string path, string message) => $"{severity}/{code}@{path}: {message}";
}
