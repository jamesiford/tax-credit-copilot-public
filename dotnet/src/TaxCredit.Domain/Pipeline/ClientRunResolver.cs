using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Pipeline;

/// <summary>What a client-programme-year is judged BY, with no payroll attached (Python <c>ResolvedStatute</c>).</summary>
/// <param name="AccountId">The client.</param>
/// <param name="State">The state.</param>
/// <param name="ProgramCode">The chosen program, always set.</param>
/// <param name="TaxYear">The tax year.</param>
/// <param name="Floors">The year's statutory floors.</param>
/// <param name="Pack">The One/Zero pack for the year.</param>
/// <param name="Window">The client's fiscal window.</param>
public sealed record ResolvedStatute(long? AccountId, string State, string ProgramCode, long TaxYear, StatutoryFloors Floors, OneZeroPack Pack, FiscalWindow Window);

/// <summary>The arguments both certified methods take (Python <c>ClientRun.engine_kwargs()</c>), so neither can drift.</summary>
/// <param name="TaxYear">The tax year.</param>
/// <param name="AnalysisStartMonth">The first measurable month.</param>
/// <param name="Pack">The pack.</param>
/// <param name="FiscalWindow">The window as dates.</param>
public sealed record EngineArgs(long TaxYear, DateOnly AnalysisStartMonth, OneZeroPack Pack, (DateOnly Begin, DateOnly End) FiscalWindow);

/// <summary>One client-programme-year, resolved and ready to compute over (Python <c>ClientRun</c>, which extends the statute with the payroll).</summary>
/// <param name="Statute">The statute and window.</param>
/// <param name="Rows">The payroll inside the window.</param>
/// <param name="StateRows">The client's payroll in this state before the window trim (what a client-wide fingerprint digests). [F04b.1]</param>
public sealed record ClientRun(ResolvedStatute Statute, IReadOnlyList<PayRow> Rows, IReadOnlyList<PayRow> StateRows)
{
    /// <summary>The client.</summary>
    public long? AccountId => Statute.AccountId;

    /// <summary>The state.</summary>
    public string State => Statute.State;

    /// <summary>The chosen program.</summary>
    public string ProgramCode => Statute.ProgramCode;

    /// <summary>The tax year.</summary>
    public long TaxYear => Statute.TaxYear;

    /// <summary>The year's statutory floors.</summary>
    public StatutoryFloors Floors => Statute.Floors;

    /// <summary>The One/Zero pack for the year.</summary>
    public OneZeroPack Pack => Statute.Pack;

    /// <summary>The client's fiscal window.</summary>
    public FiscalWindow Window => Statute.Window;

    /// <summary>
    /// Python <c>engine_kwargs()</c>. The start month is NOT <c>window.begin</c>: a year opening mid-month opens on a stub whose month-end no pay period
    /// reaches, which costs Month 1 and drops the window's real final month off the end (<c>first_measurable_month</c>).
    /// </summary>
    /// <returns>The arguments.</returns>
    public EngineArgs EngineKwargs() => new(
        TaxYear,
        OneZeroCalendar.FirstMeasurableMonth(Rows.Select(r => r.Row).ToList(), Window.Begin, Window.End),
        Pack,
        Window.Span());
}

/// <summary>
/// Resolving one client-programme-year into the inputs the engine needs (Python <c>application/queries/_client_run.py</c>). Resolution declines loudly: an
/// unauthored year, an unmapped state and an empty window each raise rather than return an empty population.
/// </summary>
/// <param name="library">The rule library.</param>
/// <param name="defaults">The program defaults.</param>
/// <param name="fiscal">The fiscal window source.</param>
/// <param name="payroll">Where payroll rows come from.</param>
public sealed class ClientRunResolver(RuleLibrary library, ProgramDefaults defaults, FiscalSource fiscal, IPayrollSource payroll)
{
    /// <summary>Python <c>resolve_statute</c>: programme, floors, rule pack and fiscal window, no payroll. [ADR-005]</summary>
    /// <param name="accountId">The client.</param>
    /// <param name="state">The state, if named.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="programCode">The program, if named.</param>
    /// <param name="requireProgram">True for a READ.</param>
    /// <returns>The statute.</returns>
    /// <exception cref="ClientRunNotAvailable">For an unmapped state, a program that cannot run, or an unauthored year.</exception>
    /// <exception cref="ProgramStateConflict">When the program and state disagree.</exception>
    public ResolvedStatute ResolveStatute(long? accountId, string? state, long taxYear, string? programCode = null, bool requireProgram = false)
    {
        string resolvedState;
        string? code;
        try
        {
            (resolvedState, code) = defaults.ResolveProgram(accountId, state, programCode, taxYear, requireProgram);
        }
        catch (ProgramNotRunnableError e)
        {
            throw new ClientRunNotAvailable(e.Message);
        }

        if (code is null)
        {
            throw new ClientRunNotAvailable($"no programme maps to state {PyStr.Repr(resolvedState)}");
        }

        StatutoryFloors floors;
        try
        {
            floors = library.ResolveStatutoryFloors(code, taxYear);
        }
        catch (Exception e) when (e is PyFileNotFoundError or PyValueError)
        {
            // An unauthored year is a decline, not a server fault: the year is genuinely uncovered.
            throw new ClientRunNotAvailable(e.Message);
        }

        var pack = library.LoadPackOneZero(code, taxYear)
            ?? throw new ClientRunNotAvailable(string.Create(CultureInfo.InvariantCulture, $"no rule pack for {resolvedState} tax year {taxYear}"));
        var convention = (string)library.ResolveTaxYearConvention(code, taxYear)["label"]!;
        return new ResolvedStatute(accountId, resolvedState, code, taxYear, floors, pack, fiscal.ClientFiscalWindow(accountId, taxYear, convention));
    }

    /// <summary>
    /// Python <c>resolve_client_run</c>: statute, fiscal window and payroll for one client-programme-year (the compute path). <paramref name="rows"/> lets a
    /// caller resolving several years hand in the payroll it already loaded; the same state filter and window trim apply.
    /// </summary>
    /// <param name="accountId">The client.</param>
    /// <param name="state">The state, if named.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="rows">The payroll already loaded, or <c>null</c> to load it.</param>
    /// <param name="programCode">The program, if named.</param>
    /// <param name="requireProgram">True for a READ.</param>
    /// <returns>The resolved run.</returns>
    /// <exception cref="ClientRunNotAvailable">When nothing can be answered, or the window holds no payroll.</exception>
    public ClientRun ResolveClientRun(long? accountId, string? state, long taxYear, IReadOnlyList<PayRow>? rows = null, string? programCode = null, bool requireProgram = false)
    {
        var statute = ResolveStatute(accountId, state, taxYear, programCode, requireProgram);
        var window = statute.Window;
        var source = rows ?? payroll.LoadPayPeriods(accountId);
        var stateRows = PayrollRows.ProgramRows(source, statute.State);
        var begin = Iso(window.Begin);
        var end = Iso(window.End);
        var inside = stateRows.Where(r => PyStr.Compare(begin, r.PayDateText()) <= 0 && PyStr.Compare(r.PayDateText(), end) <= 0).ToList();
        if (inside.Count == 0)
        {
            var scope = accountId is { } id and not 0 ? $" for account {id.ToString(CultureInfo.InvariantCulture)}" : string.Empty;
            throw new ClientRunNotAvailable($"no {statute.State} payroll inside {begin}..{end}{scope}");
        }

        return new ClientRun(statute, inside, stateRows);
    }

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}
