using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>The credit-layer tables of <c>tools/gold_projection.py</c>: <c>unit_year_master</c> and <c>unit_credit_installment</c>.</summary>
public static partial class GoldProjection
{
    /// <summary>
    /// Python <c>unit_year_master_row</c>: one unit-year with the credit layer attached. The credit columns are not optional: a dollar computed at
    /// display time cannot be reconciled to the row that produced it.
    /// </summary>
    /// <remarks>
    /// Quirks mirrored: a stair of <c>None</c> gives NULL credit columns and a 0.0000 annual credit; <c>per_job_usd</c> is the stair's rate OR, when that is
    /// falsy (an open year reading carries 0.0 for a statute without one), the series rate; <c>year_complete</c> compares a possibly-missing
    /// <c>months_with_headcount</c> (default 0) against <c>months_reachable</c>, so a present <c>None</c> raises <c>TypeError</c>; and a base year a human
    /// chose (<c>base_year_source == "override"</c>) counts as an override like a negotiated base average (WI-21).
    /// </remarks>
    /// <param name="key">The identity and labels.</param>
    /// <param name="stair">The year's stair-step reading, or <c>null</c>.</param>
    /// <param name="trend">The series it came from.</param>
    /// <param name="unitYear">The unit-year summary dictionary (<c>average_headcount</c>, <c>months_with_headcount</c>).</param>
    /// <param name="appendedAt">The run's one clock reading.</param>
    /// <returns>The row.</returns>
    /// <exception cref="PyTypeError">When <c>months_with_headcount</c> cannot be ordered against an int.</exception>
    public static GoldRow UnitYearMasterRow(UnitYearKey key, StairView? stair, BaseYearView trend, PyDict unitYear, PyDateTime appendedAt)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(trend);
        ArgumentNullException.ThrowIfNull(unitYear);
        var averageHeadcount = GoldValues.Dec(OrZero(Get(unitYear, "average_headcount")));
        var isBase = GoldValues.Flag(key.TaxYear == key.BaseYear);
        var baseAverage = GoldValues.Dec(trend.BaseAverageHeadcount);
        var netNew = stair is null ? GoldCell.Null : GoldValues.Dec(stair.NetNew);
        var complete = GoldValues.Flag(AtLeast(unitYear.TryGetValue("months_with_headcount", out var mwh) ? mwh : 0L, key.MonthsReachable));
        var threshold = stair is null ? GoldCell.Null : GoldValues.Dec(stair.Threshold);
        var qualified = GoldValues.Flag(stair is not null && GoldValues.Truthy(stair.Qualified));
        var eligibleJobs = stair is null ? GoldCell.Null : GoldValues.Dec(stair.EligibleJobs);
        var newJobs = stair is null ? GoldCell.Null : GoldValues.Dec(stair.NewJobsCreated);
        var highWater = stair is null ? GoldCell.Null : GoldValues.Dec(stair.HighWaterMark);
        var backfilled = GoldValues.Flag(stair is not null && GoldValues.Truthy(stair.Backfilled));
        var rate = stair?.PerJobUsd;
        var perJob = GoldValues.Dec(GoldValues.Truthy(rate) ? rate : trend.PerJobUsd, 4);
        var annual = GoldValues.Dec(stair is null ? 0L : stair.AnnualCreditUsd, 4);
        var baseOverridden = GoldValues.Flag(GoldValues.Truthy(trend.BaseYearOverridden) || string.Equals(key.BaseYearSource, "override", StringComparison.Ordinal));
        var hwmOverridden = GoldValues.Flag(trend.HighWaterMarkOverridden);
        return new GoldRow("unit_year_master", GoldColumns.UnitYearMaster,
        [
            Int(key.ClientId), Text(key.WorksiteId), GoldCell.OfOptionalText(key.EntityFein), Text(key.ProgramCode), Text(key.Method), Int(key.TaxYear),
            averageHeadcount, isBase, baseAverage, Text(key.BaseYearSource), netNew, Int(key.MonthsReachable), complete, GoldValues.Flag(key.Declined),
            GoldCell.OfOptionalText(key.DeclineReason), threshold, Text(key.ThresholdSource), qualified, Text(key.Status),
            Raw(key.Tier), Raw(key.Designation), Text(key.TierSource), eligibleJobs, newJobs, highWater,
            backfilled, perJob, Raw(trend.TrancheYears), annual, baseOverridden, hwmOverridden, Text(key.RunId), Int(1), GoldCell.OfDateTime(appendedAt),
        ]);
    }

    /// <summary>
    /// Python <c>unit_credit_installment_rows</c>: creation year x claimable year. A job created once pays out for years; <c>projected</c> marks an
    /// installment whose year has no payroll yet (the engine assumes the job is maintained so the forecast ceiling is visible).
    /// </summary>
    /// <remarks>"Has payroll" is set membership of the installment's year; the year cell itself is passed through unchanged, so a text year is projected and shown as text.</remarks>
    /// <param name="trend">The series.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="worksiteId">The unit.</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="method">The method name.</param>
    /// <param name="yearsWithData">The years that have payroll.</param>
    /// <param name="runId">The run.</param>
    /// <param name="appendedAt">The run's one clock reading.</param>
    /// <returns>The rows.</returns>
    /// <exception cref="PyKeyError">When an installment lacks <c>year</c>, <c>jobs_maintained</c> or <c>credit_usd</c>.</exception>
    public static IReadOnlyList<GoldRow> UnitCreditInstallmentRows(
        BaseYearView trend, BigInteger clientId, string worksiteId, string programCode, string method, IReadOnlyList<long> yearsWithData, string runId, PyDateTime appendedAt)
    {
        ArgumentNullException.ThrowIfNull(trend);
        ArgumentNullException.ThrowIfNull(yearsWithData);
        var known = yearsWithData.Select(y => (BigInteger)y).ToHashSet();
        var output = new List<GoldRow>();
        foreach (var creation in trend.TrancheEvents)
        {
            foreach (var installment in creation.Installments)
            {
                var year = installment["year"];
                output.Add(new GoldRow("unit_credit_installment", GoldColumns.UnitCreditInstallment,
                [
                    Int(clientId), Text(worksiteId), Text(programCode), Text(method), Raw(creation.CreationYear), Raw(year), GoldValues.Dec(creation.Jobs),
                    GoldValues.Dec(installment["jobs_maintained"]), GoldValues.Dec(creation.PerJobUsd, 4), GoldValues.Dec(installment["credit_usd"], 4),
                    GoldValues.Flag(!IsKnownYear(known, year)), Text(runId), Int(1), GoldCell.OfDateTime(appendedAt),
                ]));
            }
        }

        return output;
    }

    /// <summary>Python <c>year in {ints}</c> for the year cells a row can hold (an int or text; a float or bool year is not modelled, see <c>Raw</c>).</summary>
    private static bool IsKnownYear(HashSet<BigInteger> known, object? year) => year switch
    {
        long l => known.Contains(l),
        BigInteger b => known.Contains(b),
        _ => false,
    };

    /// <summary>Python <c>value &gt;= months_reachable</c> for an int on the right; other left types raise <c>TypeError</c> like Python.</summary>
    private static bool AtLeast(object? value, BigInteger reachable) => value switch
    {
        bool b => (b ? BigInteger.One : BigInteger.Zero) >= reachable,
        long l => l >= reachable,
        BigInteger b => b >= reachable,
        double d => !double.IsNaN(d) && (double.IsPositiveInfinity(d) || (!double.IsNegativeInfinity(d) && new BigInteger(Math.Floor(d)) >= reachable)),
        PyDecimal d => PyDecimalOps.Compare(d, PyDecimalOps.FromInt(reachable)) >= 0,
        _ => throw new PyTypeError($"'>=' not supported between instances of '{GoldValues.TypeName(value)}' and 'int'"),
    };
}
