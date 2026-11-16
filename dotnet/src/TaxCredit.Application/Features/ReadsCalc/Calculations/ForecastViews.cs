using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Forecast;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Triggers;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private PyDict Forecast(ReadArguments args)
    {
        var year = Year(args);
        var checkpoint = args.Date("as_of", new DateOnly((int)year, 8, 31));
        var all = Rows(args);
        var rows = FiscalRows(all, year);
        var prior = FiscalRows(all, year - 1);
        var projection = new ForecastProjection(library);
        var results = new PayrollRows(library, defaults).IterStatePacks(rows, year, args.Text("state"))
            .Select(item => projection.ProjectStateYearEnd(item.ProgramCode, year, EngineRows(rows), EngineRows(prior), checkpoint))
            .OfType<PyDict>().OrderByDescending(row => Num(row, "projected_annual_credit_usd")).ToList();
        return Dict(("as_of", checkpoint.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture)),
            ("tax_year", year), ("fiscal_year_end_month", 12L),
            ("estimated_credit_total_usd", results.Sum(r => Num(r, "projected_annual_credit_usd"))),
            ("state_count", results.Count), ("states", results));
    }

    private PyDict Performance(ReadArguments args)
    {
        var year = Year(args);
        var rows = TaggedRows(Rows(args, true), year);
        var worksite = args.Text("worksite");
        if (!string.IsNullOrEmpty(worksite))
        {
            rows = rows.Where(r => Equals(r.Get("Worksite_ID"), worksite)).ToList();
        }

        var results = new List<PyDict>();
        foreach (var item in new PayrollRows(library, defaults).IterStatePacks(rows, year, args.Text("state")))
        {
            var result = PerformanceDashboard.Run(EngineRows(item.Rows), year, item.Pack,
                perJobUsd: PyNumber.OfFloat(library.ProgramPerJobUsd(item.ProgramCode)));
            result.Set("state", item.State).Set("program_code", item.ProgramCode)
                .Set("yellow_credit_at_stake_usd", Children(result, "employees").Where(e => Text(e, "status") == "yellow").Sum(e => Num(e, "credit_at_stake_usd")));
            results.Add(result);
        }
        var totals = Dict(("green", results.Sum(r => Num((PyDict)r["summary"]!, "green"))),
            ("yellow", results.Sum(r => Num((PyDict)r["summary"]!, "yellow"))),
            ("red", results.Sum(r => Num((PyDict)r["summary"]!, "red"))), ("total", results.Sum(r => Num(r, "employee_count"))));
        return Dict(("as_of", Today), ("tax_year", year), ("scoped_worksite", worksite), ("totals", totals),
            ("yellow_credit_at_stake_usd", results.Sum(r => Num(r, "yellow_credit_at_stake_usd"))), ("states", results),
            ("anonymization_note", "Employee_ID values shown are synthetic prototype tokens (E00001 ...). The pay-period CSV omits SSN, names, and hire/term dates by design (see the BCS business-framing overview, 'Anonymity of PII'). Production tokenizes Employee_ID at the ingestion boundary; per-employee detail is releasable only under audit to authorized personnel."));
    }

    private PyDict MonthlyAlerts(ReadArguments args)
    {
        var year = Year(args);
        var units = new List<PyDict>();
        var employees = new List<PyDict>();
        var counts = Dict(("on_track", 0L), ("at_risk", 0L), ("exceeding", 0L));
        foreach (var item in new PayrollRows(library, defaults).IterStatePacks(TaggedRows(Rows(args), year), year, args.Text("state")))
        {
            var perf = PerformanceDashboard.Run(EngineRows(item.Rows), year, item.Pack);
            foreach (var unit in Children(perf, "units"))
            {
                var status = Num(unit, "yellow") == 0 && Num(unit, "red") == 0 ? "exceeding" : Num(unit, "yellow") > 0 ? "at_risk" : "on_track";
                counts.Set(status, Num(counts, status) + 1);
                units.Add(Dict(("state", item.State), ("program_code", item.ProgramCode), ("Worksite_ID", unit["Worksite_ID"]),
                    ("status", status), ("green", unit["green"]), ("yellow", unit["yellow"]), ("red", unit["red"]), ("total", unit["total"])));
            }
            foreach (var employee in Children(perf, "employees").Where(e => Text(e, "status") == "yellow"))
            {
                if (LeverSentence(employee, item) is { } sentence)
                {
                    employees.Add(Select(employee, "Employee_ID", "Worksite_ID", "avg_weekly_hours", "avg_weekly_wages",
                        "hours_gap_per_week", "wages_gap_per_week", "annual_hours_to_qualify").Set("state", item.State).Set("program_code", item.ProgramCode).Set("lever", sentence));
                }
            }
        }
        return Dict(("as_of", Today), ("tax_year", year), ("cadence", "monthly"),
            ("anchored_on", "state measuring date (one_zero.measuring_date; default last day of month)"),
            ("unit_status_counts", counts), ("unit_alerts", units), ("at_risk_employee_count", employees.Count),
            ("employee_levers", employees.OrderBy(e => Num(e, "hours_gap_per_week")).Take(50).ToList()), ("_roadmap_tag", "J3"),
            ("source", "UX-03: monthly cadence on the magical pay date; alerts distinguish on-track / at-risk / exceeding and name the specific lever to clear the threshold (e.g. 'add overtime to clear SC 32-hr threshold')."));
    }

    private PyDict Triggers(ReadArguments args)
    {
        var rows = Rows(args);
        var detected = TriggerDetector.Detect(Dictionaries(TaggedRows(rows, 2024)), Dictionaries(TaggedRows(rows, 2025)));
        var types = detected.GroupBy(t => Text(t, "type")!).Aggregate(new PyDict(), (result, group) => result.Add(group.Key, (long)group.Count()));
        return Dict(("as_of", Today), ("prior_snapshot", "Tax year 2024 (Q4 only)"), ("current_snapshot", "Tax year 2025 (full)"),
            ("trigger_count", detected.Count), ("by_type", types), ("triggers", detected),
            ("source", "Per the stakeholder meeting (5/29): triggers replace static alerts with a real differ over consecutive payroll snapshots. Production runs nightly via Azure Function."));
    }

    private static IEnumerable<PyDict> Children(PyDict row, string key) => ((System.Collections.IEnumerable)row[key]!).Cast<PyDict>();
    private static PyDict Select(PyDict row, params string[] keys) => keys.Aggregate(new PyDict(), (result, key) => result.Add(key, row.TryGetValue(key, out var value) ? value : null));

    private static string? LeverSentence(PyDict employee, PayrollRows.StatePack item)
    {
        var parts = new List<string>();
        if (Num(employee, "hours_gap_per_week") > 0)
        {
            parts.Add($"add {PyFormat.Fixed(Num(employee, "hours_gap_per_week"), 1)} hrs/wk to clear the {item.State} {PyFormat.Fixed(ReadValues.Number(item.Pack.MinWeeklyHours), 0)}-hr threshold");
        }

        if (ReadValues.Number(item.Pack.MinWeeklyWages) > 0 && Num(employee, "wages_gap_per_week") > 0)
        {
            parts.Add($"raise weekly wages by ${PyFormat.Fixed(Num(employee, "wages_gap_per_week"), 0, grouping: true)} to clear the {item.State} ${PyFormat.Fixed(ReadValues.Number(item.Pack.MinWeeklyWages), 0, grouping: true)}/wk floor");
        }

        return parts.Count == 0 ? null
            : $"{employee["Employee_ID"]} ({employee["Worksite_ID"]}) is at {PyFormat.Fixed(Num(employee, "avg_weekly_hours"), 1)} hrs/wk and ${PyFormat.Fixed(Num(employee, "avg_weekly_wages"), 0, grouping: true)}/wk avg — {string.Join("; ", parts)}.";
    }
}
