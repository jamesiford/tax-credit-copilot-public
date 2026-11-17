using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate BY (base-year family): replays every call of <c>parity/goldens/baseyear.jsonl.gz</c> (production <c>tools/baseyear.py</c>, <c>tools/unit_trend.py</c>,
/// <c>tools/designation.py</c>, <c>tools/negotiated.py</c>, <c>tools/reconcile.py</c> and the pure helpers of <c>get_unit_trend.py</c> on CPython 3.12) against the C# port,
/// bit for bit: int versus float, key order, double bits, exception type and message, and the calculation trails with their SHA-256.
/// </summary>
public sealed class BaseYearParityTests
{
    private static readonly string[] Functions =
    [
        "compute_base_year_tranches", "tranche_columns", "aggregate_units", "build_unit_series", "infer_base_year", "unit_status", "unit_trend", "unit_trend_columns",
        "detect_designation_splits", "detect_designation_splits_trail", "designation_history", "_designation_at", "all_designations", "disc_meta", "negotiated_session",
        "reconcile", "_candidate_years", "_year_benefit",
    ];

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(BaseYearInvoke.File, BaseYearInvoke.Invoke, Functions, minimumCalls: 17000, minimumErrors: 130);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(BaseYearInvoke.File, BaseYearInvoke.Invoke, ["ulp", "int-as-float", "float-as-int", "bool-flip", "key-order"], take: 4000);

    [Fact]
    public void The_trail_steps_are_recorded_and_hashed_like_pythons()
    {
        var trails = ClaimGolden.Calls(BaseYearInvoke.File)
            .Where(c => !c.ContainsKey("err") && c["out"] is PyDict && ((PyDict)c["args"]!).TryGetValue("trail", out var t) && t is PyDict).ToList();
        Assert.True(trails.Count > 200, "trail scenarios are barely covered");
        foreach (var call in trails)
        {
            var actual = (PyDict)BaseYearInvoke.Invoke(call)!;
            var expected = (PyDict)((PyDict)call["out"]!)["trail"]!;
            Assert.Equal(expected["evidence_hash"], ((PyDict)actual["trail"]!)["evidence_hash"]);
            Assert.Single((List<object?>)expected["steps"]!);
        }
    }

    [Fact]
    public void The_gold_views_of_the_real_types_read_what_the_python_attributes_hold()
    {
        var checkedYears = 0;
        foreach (var call in ClaimGolden.Calls(BaseYearInvoke.File).Where(c => !c.ContainsKey("err") && (string)c["fn"]! == "compute_base_year_tranches"))
        {
            var a = (PyDict)call["args"]!;
            var result = BaseYearInvoke.Compute(a);
            var raw = (PyDict)((PyDict)call["out"]!)["result"]!;
            var view = BaseYearView.From(result);
            Same(raw["base_average_headcount"], view.BaseAverageHeadcount);
            Same(raw["per_job_usd"], view.PerJobUsd);
            Same(raw["tranche_years"], view.TrancheYears);
            Same(raw["base_year_overridden"], view.BaseYearOverridden);
            Same(raw["high_water_mark_overridden"], view.HighWaterMarkOverridden);
            var events = (List<object?>)raw["tranche_events"]!;
            Assert.Equal(events.Count, view.TrancheEvents.Count);
            for (var i = 0; i < events.Count; i++)
            {
                var e = (PyDict)events[i]!;
                Same(e["creation_year"], view.TrancheEvents[i].CreationYear);
                Same(e["jobs"], view.TrancheEvents[i].Jobs);
                Same(e["per_job_usd"], view.TrancheEvents[i].PerJobUsd);
                Same(e["installments"], view.TrancheEvents[i].Installments.Select(d => (object?)d).ToList());
            }

            var years = (List<object?>)raw["years"]!;
            for (var i = 0; i < years.Count; i++)
            {
                var y = (PyDict)years[i]!;
                var stair = StairView.From(result.Years[i]);
                Same(y["net_new"], stair.NetNew);
                Same(y["threshold"], stair.Threshold);
                Same(y["qualified"], stair.Qualified);
                Same(y["eligible_jobs"], stair.EligibleJobs);
                Same(y["new_jobs_created"], stair.NewJobsCreated);
                Same(y["high_water_mark"], stair.HighWaterMark);
                Same(y["backfilled"], stair.Backfilled);
                Same(y["annual_credit_usd"], stair.AnnualCreditUsd);
                Same(y["per_job_usd"], stair.PerJobUsd);
                checkedYears++;
            }
        }

        Assert.True(checkedYears > 1500, "too few years compared: " + checkedYears);
    }

    [Fact]
    public void Each_year_is_priced_at_its_own_rate_and_a_tranche_holds_the_rate_of_the_year_it_opened()
    {
        // test_baseyear.py: rates that differ ON PURPOSE, because Georgia's live packs hold one rate across every year.
        var r = Series(new[] { (2021L, 100), (2022L, 105), (2023L, 110) }, new[] { (2022L, 3500), (2023L, 9999) });
        Assert.Equal(5 * 3500, (long)r.Years[0].AnnualCreditUsd);
        Assert.Equal(10 * 9999, (long)r.Years[1].AnnualCreditUsd);
        Assert.Equal(3500.0, r.TrancheEvents.Single(e => e.CreationYear == 2022).PerJobUsd);
        Assert.Equal(9999.0, r.TrancheEvents.Single(e => e.CreationYear == 2023).PerJobUsd);
    }

    [Fact]
    public void A_year_absent_from_the_map_falls_back_to_the_scalar_never_to_a_neighbouring_year()
    {
        var r = Series(new[] { (2021L, 100), (2022L, 105), (2023L, 110) }, new[] { (2023L, 4000) });
        Assert.Equal(3500.0, r.Years.Single(y => y.Year == 2022).PerJobUsd);
        Assert.Equal(4000.0, r.Years.Single(y => y.Year == 2023).PerJobUsd);
    }

    [Fact]
    public void Backfill_requalifies_a_unit_after_a_dip_and_an_int_override_keeps_its_type()
    {
        var series = new OrderedMap<long, PyNumber>();
        foreach (var (y, v) in new[] { (2021L, 100L), (2022L, 105L), (2023L, 104L), (2024L, 101L), (2025L, 103L) })
        {
            series.Set(y, PyNumber.OfInt(v));
        }

        var r = BaseYearEngine.ComputeBaseYearTranches("ga", series, 2021, new BaseYearSettings(PyNumber.OfInt(2), PyNumber.OfInt(3500), BaseAverageOverride: PyNumber.OfInt(80)));
        Assert.Equal("GA", r.State);
        Assert.True(r.BaseYearOverridden);
        Assert.True(r.Years[0].BaseAverageHeadcount.IsInt);
        Assert.True(r.ToDict()["base_average_headcount"] is long);
        var plain = BaseYearEngine.ComputeBaseYearTranches("GA", series, 2021, new BaseYearSettings(PyNumber.OfInt(2), PyNumber.OfInt(3500)));
        Assert.False(plain.Years.Single(y => y.Year == 2024).Qualified);
        Assert.True(plain.Years.Single(y => y.Year == 2025).Backfilled);
    }

    private static BaseYearResult Series((long Year, int Avg)[] avgs, (long Year, int Rate)[] rates)
    {
        var yearly = avgs.Aggregate(new OrderedMap<long, PyNumber>(), (m, p) => m.Set(p.Year, PyNumber.OfInt(p.Avg)));
        var benefit = rates.Aggregate(
            new OrderedMap<long, YearBenefit>(), (m, p) => m.Set(p.Year, new YearBenefit(PyNumber.OfInt(2), PyNumber.OfInt(p.Rate))));
        return BaseYearEngine.ComputeBaseYearTranches("GA", yearly, 2021, new BaseYearSettings(PyNumber.OfInt(2), PyNumber.OfInt(3500), BenefitByYear: benefit));
    }

    private static void Same(object? expected, object? actual)
    {
        var normalised = actual is System.Numerics.BigInteger b && b >= long.MinValue && b <= long.MaxValue ? (long)b : actual;
        Assert.Null(ClaimGolden.Compare(expected, normalised, "$"));
    }
}
