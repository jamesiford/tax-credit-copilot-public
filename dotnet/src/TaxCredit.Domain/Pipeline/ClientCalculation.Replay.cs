using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Domain.Pipeline;

public sealed partial class ClientCalculation
{
    private sealed record Replayed(
        List<GoldRow> Master, List<GoldRow> Installments, List<GoldRow> Months, List<GoldRow> Eligibility, List<GoldRow> Matrix, List<GoldRow> Periods, List<GoldRow> Summaries);

    /// <summary>
    /// Python <c>_replay_unit_series</c>: every priceable year, both methods, at unit grain with the credit layer, and the employee grain for every year too
    /// (writes are allowed to be slow; a page that cannot answer is not). Uses the same statutory lookups the read path uses rather than restating them.
    /// </summary>
    private Replayed ReplayUnitSeries(long clientId, string state, string programCode, IReadOnlyList<PayRow> payroll, string runId, PyDateTime appendedAt)
    {
        var overrides = _p.Overrides.BaseYears(clientId, programCode); // read ONCE: a failure fails the run rather than dropping a human decision
        var output = new Replayed([], [], [], [], [], [], []);
        var client = new BigInteger(clientId);
        // Payroll is per YEAR, not per method: captured on the first pass and reused, so the largest table is not doubled.
        var payrollByYear = new SortedDictionary<long, IReadOnlyList<PayRow>>();
        foreach (var method in Methods)
        {
            var perYearUnits = new OrderedMap<long, IReadOnlyList<PyDict>>();
            var reachableByYear = new OrderedMap<long, long>();
            var openYears = new HashSet<long>();
            foreach (var taxYear in UnitTrendQueryHelpers.CandidateYears(_p.Library, programCode))
            {
                ClientRun run;
                try
                {
                    run = _p.Resolver.ResolveClientRun(clientId, state, taxYear, payroll, programCode);
                }
                catch (ClientRunNotAvailable)
                {
                    continue; // declined: the year is not priced and not written
                }

                var engineRows = run.Rows.Select(r => r.Row).ToList();
                var kwargs = run.EngineKwargs();
                var result = method == "min_max"
                    ? MinMaxMethod.Run(engineRows, kwargs.TaxYear, kwargs.AnalysisStartMonth, kwargs.Pack, fiscalWindow: kwargs.FiscalWindow)
                    : PayPeriodMethod.Run(engineRows, kwargs.TaxYear, kwargs.AnalysisStartMonth, kwargs.Pack, fiscalWindow: kwargs.FiscalWindow);
                var unreached = OneZeroCalendar.UnreachableMonths(engineRows, result.Months);
                long reachable = result.Months.Count - unreached.Count;
                var yearOpen = OpenYear.IsOpen(run.Window.End, today: _config.Today);
                if (yearOpen && reachable < OpenYear.MinOpenMonths)
                {
                    continue; // two months is too early to say anything a reader should repeat
                }

                if (!yearOpen && reachable < UnitTrendQueryHelpers.MinReachableMonths)
                {
                    continue; // a twelve-month average would be mostly zeroes
                }

                var summary = Rollups.ByTwoFields(OneZeroResultTrees.Matrix(result).ToList(), "Worksite_ID", "Entity_FEIN")
                    .Select(row => Prefixed(row)).ToList();
                var units = UnitTrendTools.AggregateUnits(summary);
                perYearUnits.Set(taxYear, units);
                reachableByYear.Set(taxYear, reachable);
                output.Months.AddRange(GoldProjection.UnitMonthSummaryRows(OneZeroResultTrees.Summary(result), client, taxYear, method, runId, unreached));
                if (yearOpen)
                {
                    // "Change the denominator from 12 months to 8 or 9": the months after the checkpoint are zero because they have not happened.
                    openYears.Add(taxYear);
                    foreach (var unit in units)
                    {
                        unit.Set("average_headcount", reachable != 0 ? PyRound.Round((double)unit["total"]! / reachable, 2) : 0.0);
                        unit.Set("months_closed", reachable);
                    }
                }

                output.Eligibility.AddRange(GoldProjection.EmployeeEligibilityRows(OneZeroResultTrees.Totals(result), OneZeroResultTrees.Averages(result), client, programCode, taxYear, method, runId));
                output.Matrix.AddRange(GoldProjection.OneZeroMatrixRows(OneZeroResultTrees.Matrix(result), client, programCode, taxYear, method, runId));
                payrollByYear.TryAdd(taxYear, run.Rows);
                output.Summaries.Add(GoldProjection.RunMethodSummaryRow(OneZeroResultTrees.Facts(result), client, programCode, taxYear, method, runId, summary.Count, appendedAt));
            }

            if (perYearUnits.Count > 0)
            {
                CreditLayer(output, clientId, state, programCode, method, runId, appendedAt, perYearUnits, reachableByYear, openYears, overrides);
            }
        }

        foreach (var (taxYear, rows) in payrollByYear)
        {
            output.Periods.AddRange(GoldProjection.EmployeePeriodFactRows(rows.Select(r => r.Dict), client, programCode, taxYear, runId));
        }

        return output;
    }

    // Python `{"unit_id": row["Worksite_ID"], "fein": row["Entity_FEIN"], **row}`.
    private static PyDict Prefixed(PyDict row)
    {
        var d = new PyDict().Add("unit_id", row["Worksite_ID"]).Add("fein", row["Entity_FEIN"]);
        foreach (var kv in row)
        {
            d.Set(kv.Key, kv.Value);
        }

        return d;
    }
}
