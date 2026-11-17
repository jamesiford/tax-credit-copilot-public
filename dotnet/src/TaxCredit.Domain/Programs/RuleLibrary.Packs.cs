using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

public sealed partial class RuleLibrary
{
    /// <summary>Python <c>credit_math._load_pack</c>: a flat rule pack by file name.</summary>
    /// <param name="filename">The pack file name, relative to the rules folder.</param>
    /// <returns>The pack document.</returns>
    /// <exception cref="PyFileNotFoundError">When the file is not there.</exception>
    public PyDict LoadPack(string filename)
    {
        if (!_source.Exists(filename))
        {
            throw new PyFileNotFoundError($"rule pack not found: {filename}");
        }

        return Document(_source.ReadText(filename));
    }

    /// <summary>Python <c>credit_math.is_year_scoped</c>: a program with a <c>rules/&lt;program&gt;/</c> folder is year-scoped and resolves strictly. [ADR-005]</summary>
    /// <param name="packFile">The flat pack file name.</param>
    /// <returns>Whether the program's year folder exists.</returns>
    public bool IsYearScoped(string packFile) => _source.IsDirectory(StatutoryFloors.ProgramName(packFile));

    /// <summary>
    /// Python <c>credit_math.authored_years</c>: the tax years a program has an authored pack for, ascending. Empty means describable but
    /// <b>not calculable</b>.
    /// </summary>
    /// <param name="packFile">The flat pack file name.</param>
    /// <returns>The authored years.</returns>
    public IReadOnlyList<long> AuthoredYears(string packFile)
    {
        var program = StatutoryFloors.ProgramName(packFile);
        return _source.IsDirectory(program) ? Years(program) : [];
    }

    /// <summary>
    /// Python <c>credit_math.load_year_pack</c>: resolve a rule pack for a tax year. Once a program is year-scoped resolution <b>fails loudly</b>:
    /// a missing year raises rather than falling back to a neighbouring year or to the flat default. [ADR-005]
    /// </summary>
    /// <param name="packFile">The flat pack file name.</param>
    /// <param name="taxYear">The tax year; <c>null</c> describes the program by its latest authored year, flagged not year-resolved.</param>
    /// <returns>The pack and whether it was resolved for the requested year.</returns>
    /// <exception cref="PyFileNotFoundError">When a year-scoped program has no pack for the year.</exception>
    public (PyDict Pack, bool YearResolved) LoadYearPack(string packFile, long? taxYear)
    {
        var program = StatutoryFloors.ProgramName(packFile);
        if (!IsYearScoped(packFile))
        {
            return (LoadPack(packFile), false);
        }

        var authored = Years(program);
        if (taxYear is null)
        {
            // Describing a program ("what is GA JTC?") must not raise; any calculation path must require YearResolved.
            if (authored.Count == 0)
            {
                return (LoadPack(packFile), false);
            }

            return (Document(_source.ReadText(Within(program, $"{authored[^1].ToString(CultureInfo.InvariantCulture)}.json"))), false);
        }

        var path = Within(program, $"{taxYear.Value.ToString(CultureInfo.InvariantCulture)}.json");
        if (!_source.Exists(path))
        {
            var listed = authored.Count == 0 ? "none" : string.Join(", ", authored.Select(y => y.ToString(CultureInfo.InvariantCulture)));
            throw new PyFileNotFoundError(
                $"no rule pack for {program} tax year {taxYear.Value.ToString(CultureInfo.InvariantCulture)}. "
                + $"Authored years: {listed}. "
                + "ADR-005: statute is not inherited across years \u2014 author the "
                + "year or decline to calculate it.");
        }

        return (Document(_source.ReadText(path)), true);
    }

    /// <summary>
    /// Python <c>credit_math.resolve_tax_year_convention</c>: how a programme labels a tax year, by the year it begins or the year it ends. A statutory
    /// fact, so it lives in the rule pack; falls back to <c>begins</c> flagged <c>assumed</c> when a pack has not authored one.
    /// </summary>
    /// <param name="programCode">The program code (exact, case-sensitive).</param>
    /// <param name="taxYear">The tax year, if any.</param>
    /// <returns>The convention tree: <c>label, assumed, unconfirmed, regulation, note</c>.</returns>
    /// <exception cref="PyValueError">When the code is not a registered program.</exception>
    public PyDict ResolveTaxYearConvention(string programCode, long? taxYear = null)
    {
        var packFile = PackFileOfCode(programCode);
        PyDict pack;
        try
        {
            pack = LoadYearPack(packFile, taxYear).Pack;
        }
        catch (Exception e) when (e is PyFileNotFoundError or PyValueError or PyJsonDecodeError)
        {
            // `except (FileNotFoundError, ValueError)` in credit_math.resolve_tax_year_convention: a missing or unreadable year pack reads the flat one.
            pack = LoadPack(packFile);
        }

        var block = RuleTree.CopyOrEmpty(RuleTree.Get(pack, "tax_year_convention"));
        var label = RuleTree.Get(block, "label");
        if (label is not ("begins" or "ends"))
        {
            return new PyDict()
                .Add("label", "begins")
                .Add("assumed", true)
                .Add("unconfirmed", true)
                .Add("regulation", null)
                .Add("note", $"{programCode} has not authored a tax-year labelling convention. "
                    + "Defaulting to 'begins', which matches Georgia's regulation and every "
                    + "client currently on file. Confirm before pricing a non-calendar filer.");
        }

        return new PyDict()
            .Add("label", label)
            .Add("assumed", false)
            .Add("unconfirmed", RuleTree.Truthy(RuleTree.Get(block, "_prototype_verify")))
            .Add("regulation", RuleTree.Get(block, "regulation"))
            .Add("note", RuleTree.Get(block, "_note", string.Empty));
    }

    /// <summary>
    /// Python <c>credit_math.resolve_statutory_floors</c>: one programme-year's statutory floors from its year pack. The tax year is mandatory:
    /// a floor without a year is not a statutory fact. [ADR-005]
    /// </summary>
    /// <param name="programCode">The program code (exact, case-sensitive).</param>
    /// <param name="taxYear">The tax year; <c>null</c> raises like Python.</param>
    /// <returns>The floors.</returns>
    /// <exception cref="PyValueError">For no year, an unknown code, a program that is not year-scoped, or a pack without a floor.</exception>
    public StatutoryFloors ResolveStatutoryFloors(string programCode, long? taxYear)
    {
        if (taxYear is not { } year)
        {
            throw new PyValueError($"cannot resolve statutory floors for {programCode} without a tax year. ADR-005: the floor is a property of the year.");
        }

        var packFile = PackFileOfCode(programCode);
        var (pack, yearResolved) = LoadYearPack(packFile, year);
        var shown = year.ToString(CultureInfo.InvariantCulture);
        if (!yearResolved)
        {
            throw new PyValueError($"{programCode} is not year-scoped, so tax year {shown} cannot be resolved. Materialise its year packs first: "
                + $"python -m data.rules.materialise_years {StatutoryFloors.ProgramName(packFile)} --years {shown}");
        }

        var oneZero = RuleTree.CopyOrEmpty(RuleTree.Get(pack, "one_zero"));
        foreach (var key in new[] { "min_weekly_hours", "min_weekly_wages" })
        {
            if (RuleTree.Get(oneZero, key) is null)
            {
                throw new PyValueError($"rule pack for {programCode} tax year {shown} has no {key}.");
            }
        }

        return new StatutoryFloors(
            programCode,
            year,
            Number(oneZero["min_weekly_hours"]),
            Number(oneZero["min_weekly_wages"]),
            RuleTree.CopyOrEmpty(RuleTree.Get(oneZero, "wage_floor_basis")),
            RuleTree.CopyOrEmpty(RuleTree.Get(pack, "_year_provenance")),
            packFile);
    }

    // `rules_dir / program / name`: an empty program (a pack file named just ".json") is the rules folder itself, not a rooted path.
    private static string Within(string program, string name) => program.Length == 0 ? name : $"{program}/{name}";

    private string PackFileOfCode(string programCode) =>
        CodeToPack.TryGet(programCode, out var file)
            ? file
            : throw new PyValueError($"unknown program code {PyStr.Repr(programCode)}. Known: {string.Join(", ", CodeToPack.SortedKeys())}.");

    // `int(p.stem)` over `p.stem.isdigit()`: ASCII digits only (non-ASCII digits would parse in Python; no rules file is named that way).
    private List<long> Years(string program)
    {
        var years = new List<long>();
        foreach (var stem in _source.ListJsonStems(program))
        {
            if (stem.Length > 0 && stem.All(char.IsAsciiDigit))
            {
                years.Add(long.TryParse(stem, NumberStyles.None, CultureInfo.InvariantCulture, out var y) ? y : throw new PyUnsupportedException("authored year beyond 64 bits: " + stem));
            }
        }

        years.Sort();
        return years;
    }

    private static PyDict Document(string text) =>
        PyJson.Loads(text) as PyDict ?? throw new PyUnsupportedException("a rule pack that is not a JSON object is not modelled");

    private static PyNumber Number(object? value) => value switch
    {
        long l => PyNumber.OfInt(l),
        double d => PyNumber.OfFloat(d),
        _ => throw new PyUnsupportedException("a statutory floor that is neither an int nor a float is not modelled"),
    };
}
