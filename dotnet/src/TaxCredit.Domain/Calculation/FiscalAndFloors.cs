using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// One client's fiscal year and the tax year the statute calls it (Python <c>domain/calculation/fiscal.py</c>).
/// A fiscal window is a fact about a client; a tax year is a label an authority assigns, and they must not be conflated.
/// </summary>
/// <param name="Begin">First day.</param>
/// <param name="End">Last day.</param>
/// <param name="TaxYear">The tax year label.</param>
/// <param name="LabelConvention"><c>begins</c> or <c>ends</c> (any other text behaves as <c>ends</c>, as in Python).</param>
/// <param name="Basis"><c>client_rules</c> or <c>assumed_calendar</c>.</param>
/// <param name="Note">Explanatory note.</param>
public sealed record FiscalWindow(DateOnly Begin, DateOnly End, long TaxYear, string LabelConvention, string Basis, string Note = "")
{
    /// <summary>True when no client fiscal rule was available and a calendar year was assumed.</summary>
    public bool Assumed => Basis != "client_rules";

    /// <summary>A calendar window begins and ends in the same year.</summary>
    public bool IsCalendar => Begin.Year == End.Year;

    /// <summary>True when the two labelling conventions would disagree for this window.</summary>
    public bool ConventionMatters => !IsCalendar;

    /// <summary>The tax year under a named convention.</summary>
    /// <param name="convention">The convention.</param>
    /// <returns>The year.</returns>
    public long TaxYearUnder(string convention) => convention == "begins" ? Begin.Year : End.Year;

    /// <summary>The window as the Python <c>as_dict</c> mapping (key order preserved).</summary>
    /// <returns>The tree.</returns>
    public PyDict AsDict() => new PyDict()
        .Add("begin", Iso(Begin))
        .Add("end", Iso(End))
        .Add("tax_year", TaxYear)
        .Add("label_convention", LabelConvention)
        .Add("basis", Basis)
        .Add("assumed", Assumed)
        .Add("is_calendar", IsCalendar)
        .Add("convention_matters", ConventionMatters)
        .Add("tax_year_if_labelled_by_end", TaxYearUnder("ends"))
        .Add("tax_year_if_labelled_by_begin", TaxYearUnder("begins"))
        .Add("note", Note);

    /// <summary><c>resolve_tax_year</c>: the tax year a window belongs to under a convention.</summary>
    /// <param name="begin">First day.</param>
    /// <param name="end">Last day.</param>
    /// <param name="convention">The convention.</param>
    /// <returns>The year.</returns>
    /// <exception cref="PyValueError">When the window ends before it begins.</exception>
    public static long ResolveTaxYear(DateOnly begin, DateOnly end, string convention)
    {
        if (end < begin)
        {
            throw new PyValueError($"fiscal window ends ({Iso(end)}) before it begins ({Iso(begin)})");
        }

        return convention == "begins" ? begin.Year : end.Year;
    }

    /// <summary><c>window_from_client_rules</c>: a window taken from the client's own rule, no derivation.</summary>
    /// <param name="begin">First day.</param>
    /// <param name="end">Last day.</param>
    /// <param name="convention">The convention.</param>
    /// <param name="note">Optional note; a default is used when empty.</param>
    /// <returns>The window.</returns>
    public static FiscalWindow FromClientRules(DateOnly begin, DateOnly end, string convention, string note = "") =>
        new(begin, end, ResolveTaxYear(begin, end, convention), convention, "client_rules",
            note.Length > 0 ? note : "From the client's fiscal-year rule in the source system.");

    /// <summary><c>assumed_calendar_window</c>: a calendar year, flagged as assumed.</summary>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="convention">The convention.</param>
    /// <returns>The window.</returns>
    public static FiscalWindow AssumedCalendar(long taxYear, string convention) =>
        new(PyDate.Make((int)taxYear, 1, 1), PyDate.Make((int)taxYear, 12, 31), taxYear, convention, "assumed_calendar",
            "No fiscal-year rule on file for this client, so a calendar year is "
            + "assumed. Both labelling conventions agree for a calendar year, so "
            + "the tax year is unambiguous — but the WINDOW may not match the "
            + "client's actual accounting year.");

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
}

/// <summary>The weekly hours/wages floors a programme imposes for one tax year (Python <c>StatutoryFloors</c>).</summary>
/// <param name="ProgramCode">Programme code.</param>
/// <param name="TaxYear">Tax year.</param>
/// <param name="MinWeeklyHours">Hours floor.</param>
/// <param name="MinWeeklyWages">Wages floor.</param>
/// <param name="Basis">Basis facts (a JSON-like tree).</param>
/// <param name="Provenance">Provenance facts (a JSON-like tree).</param>
/// <param name="PackFile">Rule pack file name.</param>
public sealed record StatutoryFloors(string ProgramCode, long TaxYear, PyNumber MinWeeklyHours, PyNumber MinWeeklyWages, PyDict Basis, PyDict Provenance, string PackFile)
{
    /// <summary><c>program_name</c>: <c>ga_jtc.json</c> becomes <c>ga_jtc</c>.</summary>
    /// <param name="packFile">The file name.</param>
    /// <returns>The directory name.</returns>
    public static string ProgramName(string packFile)
    {
        ArgumentNullException.ThrowIfNull(packFile);
        return packFile.EndsWith(".json", StringComparison.Ordinal) ? packFile[..^5] : packFile;
    }

    /// <summary>True when this year's floor is an unverified placeholder (Python truthiness of either flag).</summary>
    public bool PrototypeVerify => Truthy(Get(Basis, "_prototype_verify")) || Truthy(Get(Provenance, "_prototype_verify"));

    /// <summary>The floors as the Python <c>as_dict</c> mapping (private <c>_</c> keys of <c>basis</c> hidden).</summary>
    /// <returns>The tree.</returns>
    public PyDict AsDict()
    {
        var d = new PyDict()
            .Add("program_code", ProgramCode)
            .Add("tax_year", TaxYear)
            .Add("minimum_average_weekly_hours", TrailValues.Of(MinWeeklyHours))
            .Add("minimum_average_weekly_wages_usd", TrailValues.Of(MinWeeklyWages));
        foreach (var kv in Basis.Where(kv => !kv.Key.StartsWith('_')))
        {
            d.Add(kv.Key, kv.Value);
        }

        return d.Add("prototype_verify", PrototypeVerify)
            .Add("source", $"rules/{ProgramName(PackFile)}/{TaxYear}.json");
    }

    private static object? Get(PyDict d, string key) => d.Where(kv => kv.Key == key).Select(kv => kv.Value).FirstOrDefault();

    /// <summary>Python truthiness of a JSON-like value.</summary>
    internal static bool Truthy(object? v) => v switch
    {
        null => false,
        bool b => b,
        long l => l != 0,
        double d => d != 0,
        string s => s.Length > 0,
        PyDict dict => dict.Count > 0,
        IReadOnlyList<object?> list => list.Count > 0,
        _ => true,
    };
}
