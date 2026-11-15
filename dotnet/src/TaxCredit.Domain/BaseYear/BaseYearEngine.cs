using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.BaseYear;

/// <summary>
/// The Georgia frozen-base-year tranche and backfill engine (Python <c>tools/baseyear.py</c>, CALC-07): net new jobs are measured against a frozen
/// base year with a high-water mark that persists, evaluated in tranches, with backfill. Records one step into the ambient trail.
/// </summary>
public static class BaseYearEngine
{
    /// <summary>Python <c>DEFAULT_TRANCHE_YEARS</c>.</summary>
    public const long DefaultTrancheYears = 5;

    /// <summary>Python <c>_DISC_REF</c>: the discussion item that flags the base-year treatment for partner verification.</summary>
    public const string DiscRef = "DISC-8";

    private const string Formula =
        "net_new[y] = max(0, avg[y] - base_avg); qualify if net_new >= threshold (backfill auto); tranche = 5-yr window per new high-water";

    /// <summary>Python <c>compute_base_year_tranches</c>: the per-year stair-step, the per-creation tranche schedule and both totals.</summary>
    /// <param name="state">Two-letter state code (trail label); upper-cased.</param>
    /// <param name="yearlyAvg">The Average Headcount by tax year (insertion order is irrelevant: years are sorted).</param>
    /// <param name="baseYear">The frozen base year.</param>
    /// <param name="settings">The scalars, overrides and per-year statute.</param>
    /// <returns>The result.</returns>
    /// <exception cref="PyValueError">When a credit is NaN.</exception>
    /// <exception cref="PyOverflowError">When a credit is infinite.</exception>
    public static BaseYearResult ComputeBaseYearTranches(string state, OrderedMap<long, PyNumber> yearlyAvg, long baseYear, BaseYearSettings settings)
    {
        ArgumentNullException.ThrowIfNull(state);
        ArgumentNullException.ThrowIfNull(yearlyAvg);
        ArgumentNullException.ThrowIfNull(settings);
        var stateU = PyStr.Upper(state);

        // Python: `base_average_override if base_average_override is not None else float(...)`, so an override keeps its own type.
        var baseAvg = settings.BaseAverageOverride
            ?? PyNumber.OfFloat(yearlyAvg.TryGetValue(baseYear, out var b) ? PyNum.ToDouble(b) : 0.0);
        var evalYears = yearlyAvg.Keys.Where(y => y > baseYear).Order().ToList();
        var runningHwm = settings.HighWaterMarkOverride ?? baseAvg;
        var years = new List<TrancheYear>();
        var events = new List<TrancheEvent>();
        var prevQualified = true;

        foreach (var y in evalYears)
        {
            var yearThreshold = For(settings, y, e => e.Threshold, settings.Threshold);
            var yearRate = For(settings, y, e => e.PerJobUsd, settings.PerJobUsd);
            var avg = PyNum.ToDouble(yearlyAvg.TryGetValue(y, out var a) ? a : default);
            var netNew = PyArith.Max(0.0, PyNum.Minus(avg, baseAvg));
            var qualified = netNew >= yearThreshold && netNew > 0;
            var eligibleJobs = qualified ? netNew : 0.0;
            var newJobsCreated = PyArith.Max(0.0, PyNum.Minus(avg, runningHwm));
            var backfilled = qualified && !prevQualified;
            var annualCredit = PyRound.RoundToInteger(eligibleJobs * yearRate);

            years.Add(new TrancheYear(
                y, avg, baseAvg, netNew, yearThreshold, qualified, eligibleJobs, PyNum.Max(runningHwm, avg), newJobsCreated, backfilled, annualCredit, yearRate));

            // A creation event opens a window only when the year also clears the threshold, and is priced at the CREATION year's rate for good.
            if (newJobsCreated > 0 && qualified)
            {
                events.Add(BuildTrancheEvent(y, newJobsCreated, yearRate, settings.TrancheYears, yearlyAvg, baseAvg));
            }

            runningHwm = PyNum.Max(runningHwm, avg);
            prevQualified = qualified;
        }

        var result = new BaseYearResult(
            stateU, baseYear, baseAvg, settings.Threshold, settings.PerJobUsd, settings.TrancheYears, settings.BaseAverageOverride is not null,
            settings.HighWaterMarkOverride is not null, years, events, runningHwm);
        Record(result, evalYears);
        return result;
    }

    /// <summary>Python <c>_for</c>: the year's own value when its map has one, else the scalar; never a neighbouring year's.</summary>
    private static double For(BaseYearSettings s, long year, Func<YearBenefit, PyNumber?> key, PyNumber fallback)
    {
        // Why: statute is versioned by tax year (ADR-005); a missing year inherits the caller's scalar, not the year before it.
        var entry = s.BenefitByYear is { } map && map.TryGetValue(year, out var e) ? key(e) : null;
        return PyNum.ToDouble(entry ?? fallback);
    }

    private static TrancheEvent BuildTrancheEvent(
        long creationYear, double jobs, double perJobUsd, long trancheYears, OrderedMap<long, PyNumber> yearlyAvg, PyNumber baseAvg)
    {
        var installments = new List<Installment>();
        for (var instYear = creationYear; instYear < creationYear + trancheYears; instYear++)
        {
            // No data yet for an out-year: the job is assumed maintained, so the forecast ceiling is visible.
            var jobsMaintained = yearlyAvg.TryGetValue(instYear, out var future)
                ? PyArith.Min(jobs, PyArith.Max(0.0, PyNum.Minus(PyNum.ToDouble(future), baseAvg)))
                : jobs;
            installments.Add(new Installment(instYear, PyRound.Round(jobsMaintained, 2), PyRound.RoundToInteger(jobsMaintained * perJobUsd)));
        }

        return new TrancheEvent(creationYear, jobs, perJobUsd, trancheYears, installments);
    }

    private static void Record(BaseYearResult result, List<long> evalYears)
    {
        var recorder = TrailContext.Current;
        if (recorder is null)
        {
            return;
        }

        recorder.Record(
            $"{result.State}: frozen base-year tranche evaluation",
            new PyDict()
                .Add("base_year", result.BaseYear)
                .Add("base_average_headcount", PyNum.Tree(PyNum.Round2(result.BaseAverageHeadcount)))
                .Add("threshold", PyNum.Tree(result.Threshold))
                .Add("tranche_years", result.TrancheYears)
                .Add("years_evaluated", evalYears.Select(y => (object?)y).ToList()),
            Formula,
            new PyDict()
                .Add("total_annual_credit_usd", PyNum.IntTree(result.TotalAnnualCreditUsd))
                .Add("total_tranche_lifetime_usd", PyNum.IntTree(result.TotalTrancheLifetimeUsd))
                .Add("final_high_water_mark", PyNum.Tree(PyNum.Round2(result.FinalHighWaterMark))),
            $"GA JTC base-year mechanics (pending SME form — {DiscRef})");
    }
}
