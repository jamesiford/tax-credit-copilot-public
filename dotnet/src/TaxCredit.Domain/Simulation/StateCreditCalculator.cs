using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Simulation;

/// <summary>
/// The payroll read behind <c>portfolio.chat_state_credit</c> (Python <c>load_pay_periods(account_id)</c>). A port, because reading
/// pay periods is I/O (Fabric, a CSV fixture) and the Domain stays pure.
/// </summary>
public interface IPayPeriodSource
{
    /// <summary>Loads every pay-period row of an account (<c>null</c> is the configured default account).</summary>
    /// <param name="accountId">The account, or <c>null</c>.</param>
    /// <returns>The rows.</returns>
    IReadOnlyList<PayrollRow> LoadPayPeriods(long? accountId);
}

/// <summary>The keyword arguments of <see cref="StateCreditCalculator.ChatStateCredit"/>.</summary>
/// <param name="TaxYear"><c>tax_year</c>; <c>null</c> reads the latest substantial year from the payroll.</param>
/// <param name="FiscalYearEndMonth"><c>fy_end_month</c>.</param>
/// <param name="AccountId"><c>account_id</c>.</param>
/// <param name="CurrentAverage"><c>current_average</c> already READ from a run; with it no payroll is replayed.</param>
/// <param name="PriorAverage"><c>prior_average</c>; only read together with <paramref name="CurrentAverage"/> (a falsy value is 0.0).</param>
/// <param name="ProgramCode"><c>program_code</c>: price that program of the state rather than its default.</param>
public sealed record StateCreditOptions(long? TaxYear = null, long FiscalYearEndMonth = 12, long? AccountId = null, double? CurrentAverage = null, double? PriorAverage = null, string? ProgramCode = null);

/// <summary>
/// The slice of Python <c>tools/portfolio.py</c> the what-if simulator imports: <c>chat_state_credit</c>, with <c>latest_tax_year</c> and
/// <c>_state_avg_headcount</c>. Portfolio as a whole is out of scope (it reads Gold through application services); this subset is pure
/// credit math over a rule library plus ONE payroll read, which comes through <see cref="IPayPeriodSource"/>.
/// </summary>
/// <param name="library">The rule library (Python <c>STATE_TO_PACK</c>, <c>load_pack_one_zero</c>, <c>apply_one_zero_state_credit</c>).</param>
/// <param name="payroll">The payroll read.</param>
/// <param name="today">Today's date (Python <c>date.today()</c>); the system clock when <c>null</c>.</param>
public sealed class StateCreditCalculator(RuleLibrary library, IPayPeriodSource payroll, Func<DateOnly>? today = null)
{
    /// <summary>
    /// Python <c>latest_tax_year</c>: the most recent fiscal year holding at least half of the busiest year's pay periods, so a thin tail
    /// that spills into the following January is not mistaken for the current year. No data answers the prior calendar year.
    /// </summary>
    /// <param name="fiscalYearEndMonth">The fiscal year-end month.</param>
    /// <param name="accountId">The account.</param>
    /// <returns>The tax year.</returns>
    public long LatestTaxYear(long fiscalYearEndMonth = 12, long? accountId = null)
    {
        var counts = new Dictionary<long, long>();
        foreach (var row in payroll.LoadPayPeriods(accountId))
        {
            var fy = OneZeroCalendar.FiscalYearOf(Coerce.ParseIso(row.RequirePayDate()), fiscalYearEndMonth);
            counts[fy] = counts.GetValueOrDefault(fy) + 1;
        }

        if (counts.Count == 0)
        {
            return (today ?? OpenYear.Today)().Year - 1;
        }

        var busiest = counts.Values.Max();
        return counts.Where(kv => kv.Value >= busiest * 0.5).Max(kv => kv.Key);
    }

    /// <summary>
    /// Python <c>chat_state_credit</c>: the single-state statutory credit. An unregistered state answers a <c>no_state_pack</c> dict; otherwise
    /// the pack's benefit math runs over the year's average headcount and the prior year's (replayed from the payroll when not supplied).
    /// Replaying records the engine's steps into the ambient trail, then the credit step, as Python does.
    /// </summary>
    /// <param name="state">The state (case-insensitive).</param>
    /// <param name="options">The keyword arguments.</param>
    /// <returns>The credit tree.</returns>
    public PyDict ChatStateCredit(string state, StateCreditOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(state);
        options ??= new StateCreditOptions();
        var stateU = PyStr.Upper(state);
        var fy = options.FiscalYearEndMonth;
        var taxYear = options.TaxYear ?? LatestTaxYear(fy, options.AccountId);
        if (!library.StateToPack.TryGet(stateU, out _))
        {
            return NoPack(stateU);
        }

        double current, prior;
        if (options.CurrentAverage is not null)
        {
            current = options.CurrentAverage.Value;
            // `float(prior_average or 0.0)`.
            prior = options.PriorAverage is { } p && p != 0 ? p : 0.0;
        }
        else
        {
            (current, prior) = Replay(stateU, taxYear, fy, options.AccountId);
        }

        return library.ApplyOneZeroStateCredit(RuleLibrary.CreditKey(options.ProgramCode, stateU), current, prior, null);
    }

    private PyDict NoPack(string stateU) => new PyDict()
        .Add("state", stateU)
        .Add("no_state_pack", true)
        .Add("credit_code", null)
        .Add("annual_credit_usd", 0L)
        .Add("lifetime_credit_usd", 0L)
        .Add("message", $"No state rule pack for {stateU}. Supported states: {string.Join(", ", library.StateToPack.SortedKeys())}. Federal WOTC still applies.");

    private (double Current, double Prior) Replay(string stateU, long taxYear, long fy, long? accountId)
    {
        var all = payroll.LoadPayPeriods(accountId);
        var rowsCur = all.Where(r => OneZeroCalendar.FiscalYearOf(Coerce.ParseIso(r.RequirePayDate()), fy) == taxYear).ToList();
        var rowsPrior = all.Where(r => OneZeroCalendar.FiscalYearOf(Coerce.ParseIso(r.RequirePayDate()), fy) == taxYear - 1).ToList();
        var cur = StateAverage(rowsCur, taxYear, stateU, library.LoadPackOneZero(stateU, taxYear), fy);
        var priorPack = library.LoadPackOneZero(stateU, taxYear - 1);
        var prior = priorPack is not null ? StateAverage(rowsPrior, taxYear - 1, stateU, priorPack, fy) : null;
        return (cur?.AnnualAverage ?? 0.0, prior?.AnnualAverage ?? 0.0);
    }

    // Python `_state_avg_headcount`: the pay-period method over one state's worksites, None when it has no rows.
    private static OneZeroResult? StateAverage(IReadOnlyList<PayrollRow> rows, long taxYear, string state, OneZeroPack? pack, long fy)
    {
        var prefix = state + "_";
        var stateRows = rows.Where(r => (r.RequireWorksiteId() ?? throw new PyAttributeError("'NoneType' object has no attribute 'startswith'"))
            .StartsWith(prefix, StringComparison.Ordinal)).ToList();
        return stateRows.Count == 0
            ? null
            : PayPeriodMethod.Run(stateRows, taxYear, OneZeroCalendar.FiscalWindowStart(taxYear, fy), pack ?? throw new PyAttributeError("'NoneType' object has no attribute 'methodology'"), fy);
    }
}
