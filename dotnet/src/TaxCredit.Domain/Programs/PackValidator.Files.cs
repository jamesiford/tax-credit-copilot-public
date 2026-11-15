using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

public sealed partial class PackValidator
{
    /// <summary>Python <c>validate_pack</c>: validates one base pack or year pack file (a year pack is a <c>&lt;program&gt;/&lt;year&gt;.json</c>).</summary>
    /// <param name="relativePath">The file, relative to the rules folder, with <c>/</c> separators.</param>
    /// <param name="yearsAuthored">Whether the program has authored year packs.</param>
    /// <returns>The report; a file that is not JSON is one <c>unreadable</c> error rather than an exception.</returns>
    public PackReport ValidatePack(string relativePath, bool yearsAuthored = false)
    {
        ArgumentNullException.ThrowIfNull(relativePath);
        var name = relativePath[(relativePath.LastIndexOf('/') + 1)..];
        var kind = PackKinds.IsYearName(StemOf(name)) ? PackKinds.Year : PackKinds.Base;
        var shown = _source.RulesDirectory + "/" + relativePath;
        object? pack;
        try
        {
            pack = PyJson.Loads(_source.ReadText(relativePath));
        }
        catch (Exception exc) when (exc is PyValueError or PyJsonDecodeError or PyFileNotFoundError)
        {
            // `except (OSError, ValueError)`: a JSONDecodeError and a too-long integer are ValueErrors; a missing file is an OSError.
            var report = new PackReport(shown, kind);
            report.Add("error", "unreadable", $"cannot read as JSON: {exc.Message}");
            return report;
        }

        return ValidateDocument(pack, name, kind, yearsAuthored, shown);
    }

    /// <summary>
    /// Python <c>validate_all</c>: every base pack, year pack and the registry itself under the rules folder, in file-name order; a base pack is
    /// followed by its year packs.
    /// </summary>
    /// <returns>One report per file.</returns>
    /// <exception cref="RegistryError">When the program registry cannot be read.</exception>
    public IReadOnlyList<PackReport> ValidateAll()
    {
        var registered = new Dictionary<string, ProgramEntry>(StringComparer.Ordinal);
        foreach (var entry in _library.LoadRegistry().Entries)
        {
            registered[entry.PackFile] = entry;
        }

        var seen = new List<(object? Code, string Name)>();
        var reports = new List<PackReport>();
        foreach (var name in SortedJsonNames(string.Empty))
        {
            var stem = StemOf(name);
            var years = SortedJsonNames(stem).Where(n => StemOf(n).Length > 0 && StemOf(n).All(char.IsAsciiDigit)).ToList();
            var report = ValidatePack(name, yearsAuthored: years.Count > 0);
            var baseDocument = LoadDict(name);
            RegistryChecks(report, name, baseDocument, registered, seen);
            reports.Add(report);
            reports.AddRange(years.Select(year => YearReport($"{stem}/{year}", baseDocument)));
        }

        return reports;
    }

    private PackReport YearReport(string relativePath, PyDict? baseDocument)
    {
        var report = ValidatePack(relativePath, yearsAuthored: true);
        var year = LoadDict(relativePath);
        if (baseDocument is not null && year is not null)
        {
            foreach (var key in new[] { "credit", "jurisdiction" })
            {
                if (!PyEquality.Equal(RuleTree.Get(PackSemanticChecks.Mapping(RuleTree.Get(year, key)), "code"), RuleTree.Get(PackSemanticChecks.Mapping(RuleTree.Get(baseDocument, key)), "code")))
                {
                    report.Add("error", "year_pack_mismatch", $"{key}.code differs from the base pack");
                }
            }
        }

        return report;
    }

    /// <summary>Python <c>_registry_checks</c>: a base pack is listed, its credit code is unique and it matches its entry.</summary>
    private static void RegistryChecks(PackReport report, string name, PyDict? baseDocument, Dictionary<string, ProgramEntry> registered, List<(object? Code, string Name)> seen)
    {
        if (!registered.ContainsKey(name))
        {
            report.Add("error", "unregistered", $"{name} is not listed in the program registry");
        }

        var credit = PackSemanticChecks.Mapping(baseDocument is null ? null : RuleTree.Get(baseDocument, "credit"));
        var code = RuleTree.Get(credit, "code");
        if (!RuleTree.Truthy(code))
        {
            return;
        }

        // `code in seen` hashes the code: a list or a mapping there is a TypeError, as it is for a dict key in Python.
        if (code is List<object?> or PyDict)
        {
            throw new PyTypeError($"unhashable type: '{ProximityCoerce.TypeName(code)}'");
        }

        var at = seen.FindIndex(s => PyEquality.Equal(s.Code, code));
        if (at >= 0)
        {
            report.Add("error", "duplicate_code", $"credit code {RuleTree.Str(code)} is already used by {seen[at].Name}");
            seen[at] = (seen[at].Code, name);
        }
        else
        {
            seen.Add((code, name));
        }

        if (registered.TryGetValue(name, out var entry) && !PyEquality.Equal(entry.Code, code))
        {
            report.Add("error", "registry_mismatch", $"registry says {entry.Code}, pack says {RuleTree.Str(code)}");
        }
    }

    /// <summary>Python <c>_load_dict</c>: the file as a mapping, or <c>null</c> when it cannot be read or is not an object.</summary>
    private PyDict? LoadDict(string relativePath)
    {
        try
        {
            return PyJson.Loads(_source.ReadText(relativePath)) as PyDict;
        }
        catch (Exception exc) when (exc is PyValueError or PyJsonDecodeError or PyFileNotFoundError)
        {
            return null;
        }
    }

    // Python sorts pathlib paths of one folder, which compares the file names.
    private List<string> SortedJsonNames(string folder) =>
        PySort.Sorted(_source.ListJsonStems(folder).Select(stem => stem + ".json"), n => n, PyStr.Comparer);

    private static string StemOf(string name) => name.EndsWith(".json", StringComparison.OrdinalIgnoreCase) ? name[..^5] : name;
}
