using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Pre-flight cleanup common to both methods (Python <c>onezero.preprocess</c>; BA-01, BA-02, BA-05).</summary>
public static class OneZeroPreprocessing
{
    /// <summary>
    /// Trims to the analysis window on pay date, collapses duplicate (employee, unit, start, end) lines by summing, and
    /// (unless BA-05 keeps them) drops zero-hour lines. Returns a new list; the input rows are never mutated.
    /// </summary>
    /// <param name="rows">Payroll rows.</param>
    /// <param name="taxYear">Fiscal year label.</param>
    /// <param name="fiscalYearEndMonth">Last month of the fiscal year (12 = calendar).</param>
    /// <param name="fiscalWindow">Explicit client window (BA-01); wins over the derived fiscal year.</param>
    /// <param name="methodology">Methodology; defaults when null.</param>
    /// <param name="recorder">Trail recorder; the ambient one when null.</param>
    /// <returns>The preprocessed rows with Hours_Worked and Gross_Wages coerced to floats.</returns>
    public static List<PayrollRow> Preprocess(
        IReadOnlyList<PayrollRow> rows,
        long taxYear,
        long fiscalYearEndMonth = 12,
        (DateOnly Begin, DateOnly End)? fiscalWindow = null,
        OneZeroMethodology? methodology = null,
        TrailRecorder? recorder = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        recorder ??= TrailContext.Current;
        methodology ??= new OneZeroMethodology();
        var inCount = rows.Count;

        var inWindow = new List<PayrollRow>();
        foreach (var r in rows)
        {
            var payDate = Coerce.ParseIso(r.RequirePayDate());
            var keep = fiscalWindow is { } w
                ? w.Begin <= payDate && payDate <= w.End
                : OneZeroCalendar.FiscalYearOf(payDate, fiscalYearEndMonth) == taxYear;
            if (keep)
            {
                inWindow.Add(r);
            }
        }

        var droppedOffYear = inCount - inWindow.Count;

        var grouped = new OrderedDictionary<(string?, string?, string?, string?), PayrollRow>();
        foreach (var r in inWindow)
        {
            var key = (r.RequireEmployeeId(), r.RequireWorksiteId(), r.RequireStart(), r.RequireEnd());
            if (grouped.TryGetValue(key, out var existing))
            {
                var hours = PyRound.Round(Coerce.ToFloat(existing.RequireHours()) + Coerce.ToFloat(r.RequireHours()), 2);
                var wages = PyRound.Round(Coerce.ToFloat(existing.RequireWages()) + Coerce.ToFloat(r.RequireWages()), 2);
                grouped[key] = existing.WithAmounts(RowCell.OfFloat(hours), RowCell.OfFloat(wages));
            }
            else
            {
                var hours = Coerce.ToFloat(r.RequireHours());
                var wages = Coerce.ToFloat(r.RequireWages());
                grouped[key] = r.WithAmounts(RowCell.OfFloat(hours), RowCell.OfFloat(wages));
            }
        }

        var collapsed = grouped.Values.ToList();
        var collapsedCount = inWindow.Count - collapsed.Count;

        List<PayrollRow> output;
        var droppedZeroHours = 0;
        if (methodology.CountZeroHourPeriods)
        {
            output = collapsed;
        }
        else
        {
            output = collapsed.Where(r => Coerce.ToFloat(r.RequireHours()) > 0).ToList();
            droppedZeroHours = collapsed.Count - output.Count;
        }

        recorder?.Record(
            "onezero.preprocess",
            new PyDict().Add("rows_in", (long)inCount).Add("tax_year", taxYear),
            "filter(PaycheckDate in window) -> collapse_by(EE,Unit,PPS,PPE)" + (methodology.CountZeroHourPeriods ? string.Empty : " -> drop hours==0"),
            new PyDict()
                .Add("rows_out", (long)output.Count)
                .Add("dropped_off_tax_year", (long)droppedOffYear)
                .Add("collapsed_duplicates", (long)collapsedCount)
                .Add("dropped_zero_hours", (long)droppedZeroHours),
            "BCS business-framing doc; GA xlsx pre-processing notes; BA-01, BA-02, BA-05");
        return output;
    }
}
