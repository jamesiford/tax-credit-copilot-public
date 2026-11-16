using System.Globalization;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

/// <summary>Source-backed statutory discovery; accepted Gold answers belong to ReadsStoredPortfolioBriefs instead.</summary>
/// <param name="payroll">The selected source; errors must propagate.</param>
/// <param name="library">The host's rule library, including wage/ingestion collaborators.</param>
/// <param name="defaults">Program enumeration in registry order.</param>
/// <param name="referenceData">Hire dates unavailable in the pay-period source.</param>
/// <param name="clock">The host/replay clock.</param>
public sealed partial class ReadsPortfolioService(
    IPayrollSource payroll, RuleLibrary library, ProgramDefaults defaults, IPortfolioReferenceData referenceData, IClock clock)
{
    /// <summary>Ignores thin fiscal tails, retaining Python's prior-calendar-year default for an empty configured source.</summary>
    public long LatestTaxYear(long fyEndMonth = 12, long? accountId = null)
    {
        var counts = payroll.LoadPayPeriods(accountId).GroupBy(r => Year(r, fyEndMonth))
            .ToDictionary(g => g.Key, g => g.Count());
        return counts.Count == 0 ? clock.UtcNow.Year - 1
            : counts.Where(p => p.Value >= counts.Values.Max() * 0.5).Max(p => p.Key);
    }

    /// <summary>Builds one tile per priced program, federal hire credit, and distinct-employee no-pack state.</summary>
    public IReadOnlyList<PyDict> BuildPortfolio(long taxYear, long fyEndMonth = 12, long? accountId = null)
    {
        var all = payroll.LoadPayPeriods(accountId);
        if (all.Count == 0)
        {
            throw new ClientRunNotAvailable("no payroll in the active data source");
        }
        var current = all.Where(r => Year(r, fyEndMonth) == taxYear).ToList();
        var prior = all.Where(r => Year(r, fyEndMonth) == taxYear - 1).ToList();
        var tiles = new List<PyDict>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (state, code) in defaults.StatePrograms())
        {
            var tile = StateTile(current, prior, (state, code, taxYear, fyEndMonth));
            if (tile is not null)
            {
                tiles.Add(tile);
                seen.Add(state);
            }
        }
        if (FederalTile(taxYear) is { } federal)
        {
            tiles.Add(federal);
        }
        foreach (var state in current.Select(StatePrefix).Distinct(StringComparer.Ordinal).Order(PyStr.Comparer))
        {
            if (!seen.Contains(state) && state != "US")
            {
                var employees = current.Where(r => Worksite(r).StartsWith(state + "_", StringComparison.Ordinal))
                    .Select(r => r.Get("Employee_ID")).Distinct().Count();
                tiles.Add(NoPackTile(state, employees));
            }
        }
        return tiles;
    }

    /// <summary>Prices stored averages without replay; when omitted, explicitly performs a source-backed state calculation.</summary>
    public PyDict StateCredit(string state, long taxYear, long? accountId = null,
        double? currentAverage = null, double? priorAverage = null, string? programCode = null, long fyEndMonth = 12)
    {
        ArgumentNullException.ThrowIfNull(state);
        var upper = state.ToUpperInvariant();
        var key = RuleLibrary.CreditKey(programCode, upper);
        if (!library.StateToPack.Contains(upper))
        {
            return new PyDict().Add("state", upper).Add("no_state_pack", true).Add("credit_code", null)
                .Add("annual_credit_usd", 0L).Add("lifetime_credit_usd", 0L)
                .Add("message", $"No state rule pack for {upper}. Supported states: {string.Join(", ", library.StateToPack.SortedKeys())}. Federal WOTC still applies.");
        }
        defaults.CheckProgramState(upper, programCode);
        if (currentAverage is { } average)
        {
            return library.ApplyOneZeroStateCredit(key, average, priorAverage ?? 0.0, null);
        }
        var all = payroll.LoadPayPeriods(accountId);
        if (all.Count == 0)
        {
            throw new ClientRunNotAvailable("no payroll in the active data source");
        }
        var current = RunState(all.Where(r => Year(r, fyEndMonth) == taxYear).ToList(), upper, key, taxYear, fyEndMonth);
        var prior = RunState(all.Where(r => Year(r, fyEndMonth) == taxYear - 1).ToList(), upper, key, taxYear - 1, fyEndMonth);
        return library.ApplyOneZeroStateCredit(key, current?.AnnualAverage ?? 0.0, prior?.AnnualAverage ?? 0.0, null);
    }

    private OneZeroResult? RunState(IReadOnlyList<PayRow> rows, string state, string key, long year, long endMonth)
    {
        var pack = library.LoadPackOneZero(key, year);
        if (pack is null)
        {
            return null;
        }
        var stateRows = rows.Where(r => Worksite(r).StartsWith(state + "_", StringComparison.Ordinal)).Select(r => r.Row).ToList();
        return stateRows.Count == 0 ? null
            : PayPeriodMethod.Run(stateRows, year, OneZeroCalendar.FiscalWindowStart(year, endMonth), pack, fiscalYearEndMonth: endMonth);
    }

    private static long Year(PayRow row, long endMonth) =>
        OneZeroCalendar.FiscalYearOf(DateOnly.ParseExact(row.PayDateText(), "yyyy-MM-dd", CultureInfo.InvariantCulture), endMonth);

    private static string Worksite(PayRow row) => row.Get("Worksite_ID") as string ?? "";
    private static string StatePrefix(PayRow row) => Worksite(row).Split('_', 2)[0];
}
