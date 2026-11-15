using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Simulation;

/// <summary>The keyword arguments of <see cref="OneZeroLever.Apply"/> (Python <c>apply_onezero_lever</c>).</summary>
/// <param name="Action"><c>adjust_hours</c>, <c>adjust_wages</c>, <c>add_headcount</c>, <c>remove_headcount</c>; anything else changes nothing.</param>
/// <param name="Magnitude">Hours a week, percent, or a head count (Python takes an int or a float).</param>
/// <param name="Pack">The eligibility parameters.</param>
/// <param name="State">The state, as written into the detail text and the clone ids.</param>
/// <param name="Fein">The entity scope shown in the detail text; empty or <c>null</c> shows none.</param>
/// <param name="HireWeeklyHours">WI-22: hours a week of each new head; <c>null</c> keeps the template's hours.</param>
/// <param name="HireHourlyRate">WI-22: pay an hour of each new head; <c>null</c> keeps the template's rate.</param>
public sealed record LeverRequest(string Action, double Magnitude, OneZeroPack Pack, string State, string? Fein = null, double? HireWeeklyHours = null, double? HireHourlyRate = null);

/// <summary>
/// Python <c>apply_onezero_lever</c>: applies a J2 simulator lever to a COPY of the rows and says what it did. Levers: <c>adjust_hours</c>
/// (hours a week delta), <c>adjust_wages</c> (percent), <c>add_headcount</c> (clone the highest-hours employee so the synthetic heads land
/// in real major pay periods), <c>remove_headcount</c> (drop the lowest-hours employees).
/// </summary>
/// <remarks>
/// Why a copy: Python <c>copy.deepcopy(rows)</c>; <see cref="PayrollRow"/> is immutable, so a <c>with</c> copy is the same isolation. Columns
/// the port does not model (such as <c>Tax_Year</c>) are not carried onto the result rows (findings: the engine models ten columns).
/// </remarks>
public static class OneZeroLever
{
    /// <summary>Applies the lever.</summary>
    /// <param name="rows">The pay-period rows (never modified).</param>
    /// <param name="request">The lever.</param>
    /// <returns>The mutated rows and the human-readable detail.</returns>
    public static (IReadOnlyList<PayrollRow> Rows, string Detail) Apply(IReadOnlyList<PayrollRow> rows, LeverRequest request)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(request);
        var sim = rows.ToList();
        var suffix = string.IsNullOrEmpty(request.Fein) ? string.Empty : $" (FEIN {request.Fein})";
        var state = request.State;
        var magnitude = request.Magnitude;
        switch (request.Action)
        {
            case "adjust_hours":
                for (var i = 0; i < sim.Count; i++)
                {
                    var weeks = PyArith.Max(Days(sim[i]) / 7.0, 0.1);
                    sim[i] = sim[i] with { HoursWorked = RowCell.OfFloat(PyArith.Max(0.0, RowOps.Float(sim[i].RequireHours(), "Hours_Worked") + (magnitude * weeks))) };
                }

                return (sim, $"Adjusted weekly hours by {PyFormat.Fixed(magnitude, 1, plus: true)} hrs/wk across all {state} pay periods{suffix}");
            case "adjust_wages":
                var factor = 1.0 + (magnitude / 100.0);
                for (var i = 0; i < sim.Count; i++)
                {
                    sim[i] = sim[i] with { GrossWages = RowCell.OfFloat(PyArith.Max(0.0, RowOps.Float(sim[i].RequireWages(), "Gross_Wages") * factor)) };
                }

                return (sim, $"Adjusted gross wages by {PyFormat.Fixed(magnitude, 1, plus: true)}% across all {state} pay periods{suffix}");
            case "remove_headcount":
                return (RemoveLowest(sim, magnitude), $"Removed {RowOps.Int(magnitude)} lowest-hours employees from {state}");
            case "add_headcount":
                return AddHeads(rows, sim, request);
            default:
                return (sim, $"Unknown lever '{request.Action}'; no change applied");
        }
    }

    // `(end - start).days`, the End parsed first as Python evaluates the subtraction left to right.
    private static long Days(PayrollRow r)
    {
        var end = Coerce.ParseIso(r.RequireEnd());
        var start = Coerce.ParseIso(r.RequireStart());
        return end.DayNumber - start.DayNumber;
    }

    private static List<PayrollRow> RemoveLowest(List<PayrollRow> sim, double magnitude)
    {
        var totals = new OrderedDictionary<NullableKey, double>();
        foreach (var r in sim)
        {
            var key = new NullableKey(r.RequireEmployeeId());
            totals[key] = (totals.TryGetValue(key, out var seen) ? seen : 0.0) + RowOps.Float(r.RequireHours(), "Hours_Worked");
        }

        var ordered = PySort.Sorted(totals, kv => kv.Value, PySort.FloatComparer);
        var take = RowOps.SliceEnd(RowOps.Int(magnitude), ordered.Count);
        var remove = ordered.Take(take).Select(kv => kv.Key).ToHashSet();
        return sim.Where(r => !remove.Contains(new NullableKey(r.RequireEmployeeId()))).ToList();
    }

    private static (IReadOnlyList<PayrollRow> Rows, string Detail) AddHeads(IReadOnlyList<PayrollRow> rows, List<PayrollRow> sim, LeverRequest q)
    {
        var hoursByEmployee = new OrderedDictionary<NullableKey, double>();
        foreach (var r in sim)
        {
            var key = new NullableKey(r.RequireEmployeeId());
            hoursByEmployee[key] = (hoursByEmployee.TryGetValue(key, out var seen) ? seen : 0.0) + RowOps.Float(r.RequireHours(), "Hours_Worked");
        }

        if (hoursByEmployee.Count == 0)
        {
            return (sim, "No template employee to clone; no heads added");
        }

        var template = PySort.MaxBy(hoursByEmployee.ToList(), kv => kv.Value, PySort.FloatComparer).Key;
        var templateRows = rows.Where(r => new NullableKey(r.RequireEmployeeId()) == template).ToList();
        var specified = q.HireWeeklyHours is not null || q.HireHourlyRate is not null;
        var templateHours = PySum.Sum(templateRows.Select(r => RowOps.Float(r.RequireHours(), "Hours_Worked")).ToList());
        var templateRate = templateHours > 0 ? PySum.Sum(templateRows.Select(r => RowOps.Float(r.RequireWages(), "Gross_Wages")).ToList()) / templateHours : 0.0;
        var count = RowOps.Int(q.Magnitude);
        for (long n = 0; n < count; n++)
        {
            foreach (var r in templateRows)
            {
                sim.Add(Clone(r, q, (n, specified, templateRate)));
            }
        }

        var detail = specified ? SpecifiedDetail(q, count, templateRate) : $"Added {count} full-time heads (cloned from {template.Value ?? "None"}) in {q.State}";
        return (sim, detail);
    }

    private static PayrollRow Clone(PayrollRow r, LeverRequest q, (long N, bool Specified, double TemplateRate) ctx)
    {
        var clone = r with { EmployeeId = RowCell.OfText($"SIM_{q.State}_{ctx.N:000}") };
        if (!ctx.Specified)
        {
            var hours = PyArith.Max(RowOps.Float(r.RequireHours(), "Hours_Worked"), ProximityCoerce.ToFloat(q.Pack.MinWeeklyHours) + 5.0);
            var wages = PyArith.Max(RowOps.Float(r.RequireWages(), "Gross_Wages"), PyArith.Max(ProximityCoerce.ToFloat(q.Pack.MinWeeklyWages), 700.0) + 50.0);
            return clone.WithAmounts(RowCell.OfFloat(hours), RowCell.OfFloat(wages));
        }

        var weeks = PyArith.Max((Days(r) + 1) / 7.0, 1 / 7.0);
        var specifiedHours = q.HireWeeklyHours is { } h ? h * weeks : RowOps.Float(r.RequireHours(), "Hours_Worked");
        var rate = q.HireHourlyRate ?? ctx.TemplateRate;
        return clone.WithAmounts(RowCell.OfFloat(PyArith.Max(0.0, specifiedHours)), RowCell.OfFloat(PyArith.Max(0.0, specifiedHours * rate)));
    }

    private static string SpecifiedDetail(LeverRequest q, long count, double templateRate)
    {
        var hoursText = q.HireWeeklyHours is { } h ? $"{PyFormat.General(h)} hrs/wk" : "the template's hours";
        var rateText = q.HireHourlyRate is { } r ? $"${PyFormat.Fixed(r, 2, grouping: true)}/hr" : $"${PyFormat.Fixed(templateRate, 2, grouping: true)}/hr";
        var role = OneZeroSimulation.DescribeRole(q.HireWeeklyHours, q.HireHourlyRate ?? templateRate, q.Pack);
        return $"Added {count} heads at {hoursText} and {rateText} in {q.State} \u2014 {role}";
    }
}
