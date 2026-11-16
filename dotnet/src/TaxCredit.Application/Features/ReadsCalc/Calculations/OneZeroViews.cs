using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private static readonly string[] MethodDocumentation =
        ["the Pay Period Method (preferred)", "the Min Max Method (fallback)", "the BCS business-framing overview"];
    private static readonly string[] OneZeroRoadmapTags = ["H1", "H2", "H3", "H5", "I1", "I2", "L3", "L4"];

    private PyDict OneZero(ReadArguments args)
    {
        var year = Year(args);
        var method = (args.Text("method", "both") ?? "both").ToLowerInvariant();
        if (method is not ("both" or "pay_period" or "min_max"))
        {
            throw new ReadRefusalException(400, "method must be pay_period | min_max | both");
        }

        var all = Rows(args, true);
        var fein = args.Text("fein");
        var rows = FiscalRows(all, year).Where(r => string.IsNullOrEmpty(fein) || Equals(r.Get("Entity_FEIN"), fein)).ToList();
        var prior = FiscalRows(all, year - 1).Where(r => string.IsNullOrEmpty(fein) || Equals(r.Get("Entity_FEIN"), fein)).ToList();
        var results = new PayrollRows(library, defaults).IterStatePacks(rows, year, args.Text("state"))
            .Select(item => StateEntry(item, prior, year, method)).ToList();
        return Dict(("as_of", Today), ("tax_year", year), ("method", method), ("fein", fein),
            ("fiscal_year_end_month", 12L),
            ("method_docs", MethodDocumentation),
            ("row_count", rows.Count), ("state_count", results.Count), ("results", results));
    }

    private PyDict StateEntry(PayrollRows.StatePack item, IReadOnlyList<PayRow> prior, long year, string method)
    {
        var (pack, threshold, negotiated) = Negotiated(item.State, item.Pack);
        var pp = method is "both" or "pay_period" ? Run(item.Rows, year, pack) : null;
        var mm = method is "both" or "min_max" ? Run(item.Rows, year, pack, "min_max") : null;
        var primary = pp ?? mm!;
        var priorAverage = PriorAverage(prior, item, year, method);
        var credit = library.ApplyOneZeroStateCredit(item.ProgramCode, primary.AnnualAverage, priorAverage, threshold);
        var byFein = Rollups.ByField(OneZeroResultTrees.Matrix(primary), "Entity_FEIN");
        foreach (var (fein, aggregation) in byFein)
        {
            ((PyDict)aggregation!).Set("entity_name", EntityName(fein));
        }

        var bySite = Rollups.ByTwoFields(OneZeroResultTrees.Matrix(primary), "Worksite_ID", "Entity_FEIN");
        foreach (var row in bySite)
        {
            row.Set("entity_name", EntityName(Text(row, "Entity_FEIN")!));
        }

        var (entityView, finalCredit) = EntityView(item.ProgramCode, pack, byFein, credit);
        var result = Dict(("state", item.State), ("program_code", item.ProgramCode), ("rule_pack_citation", pack.Citation),
            ("method", method), ("eligibility_floors", Floors(pack, year)), ("negotiated_override", negotiated),
            ("eligible_employee_count", primary.EligibleEmployees.Count), ("part_time_eligible_count", primary.EligibleEmployees.Count(e => e.Weight < 1)),
            ("eligibility_sample", OneZeroResultTrees.Averages(primary).Where(e => ReadValues.Bool(e["eligible"])).Take(50)
                .Select(e => Select(e, "Employee_ID", "avg_weekly_hours", "avg_weekly_wages", "passed_hours", "passed_wages", "weight")).ToList()),
            ("pay_period_summary", pp is null ? [] : OneZeroResultTrees.Summary(pp)), ("min_max_summary", mm is null ? [] : OneZeroResultTrees.Summary(mm)),
            ("pay_period_average_headcount", pp?.AnnualAverage ?? 0), ("min_max_average_headcount", mm?.AnnualAverage ?? 0),
            ("average_headcount", primary.AnnualAverage), ("prior_year_average_headcount", priorAverage),
            ("yoy_delta", PyRound.Round(primary.AnnualAverage - priorAverage, 2)), ("fein_breakdown", byFein),
            ("site_entity_breakdown", bySite), ("multi_entity_sites", bySite.GroupBy(r => Text(r, "Worksite_ID"))
                .Where(g => g.Select(r => Text(r, "Entity_FEIN")).Distinct().Count() > 1).Select(g => g.Key).Order(StringComparer.Ordinal).ToList()),
            ("entity_combination_view", entityView), ("min_max_anchors", Anchors(mm)), ("credit_estimate", finalCredit),
            ("data_quality_flags", Flags(pp).Concat(Flags(mm)).ToList()),
            ("_roadmap_tag", OneZeroRoadmapTags));
        if (pp is not null && mm is not null)
        {
            result.Set("reconciliation", ReconciliationView(pp, mm));
        }

        return result;
    }

    private double PriorAverage(IReadOnlyList<PayRow> rows, PayrollRows.StatePack item, long year, string method)
    {
        var stateRows = rows.Where(r => (r.Get("Worksite_ID") as string)?.StartsWith(item.State + "_", StringComparison.Ordinal) == true).ToList();
        if (stateRows.Count == 0)
        {
            return 0;
        }

        var priorPack = library.LoadPackOneZero(item.ProgramCode, year - 1);
        return priorPack is null ? 0 : Run(stateRows, year - 1, priorPack, method == "min_max" ? "min_max" : "pay_period").AnnualAverage;
    }

    private (OneZeroPack Pack, double? Threshold, PyDict? Override) Negotiated(string state, OneZeroPack pack)
    {
        var entry = lookups.Entries("negotiated_overrides", 0).LastOrDefault(e => e.Key == state);
        if (entry is null)
        {
            return (pack, null, null);
        }

        var value = (PyDict)PyJson.Loads(entry.ValueJson)!;
        if (value.TryGetValue("wage_standard_weekly", out var wage) && wage is not null)
        {
            pack = pack with { MinWeeklyWages = PyNumber.OfFloat(ReadValues.Number(wage)) };
        }

        return (pack, value.TryGetValue("min_jobs", out var minimum) && minimum is not null ? ReadValues.Number(minimum) : null, value);
    }

    private static PyDict Floors(OneZeroPack pack, long year) =>
        Dict(("tax_year", year), ("min_weekly_hours", pack.MinWeeklyHours), ("min_weekly_wages", pack.MinWeeklyWages),
            ("wage_test_applies", ReadValues.Number(pack.MinWeeklyWages) > 0),
            ("pt_band_hours", pack.PtBandHours is { } band ? new[] { band.Low, band.High } : null),
            ("pt_weight", pack.PtWeight), ("measuring_date", pack.MeasuringDate), ("entity_combination", pack.EntityCombination));

    private static List<PyDict> Anchors(OneZeroResult? result) => result is null ? [] : result.EligibleEmployees
        .Where(e => e.Span is not null).Take(50).Select(e => Dict(("Employee_ID", e.EmployeeId),
            ("anchor_min_date", e.Span!.FirstStart), ("anchor_max_date", e.Span.LastEnd), ("weeks_worked", e.WeeksWorked))).ToList();

    private static IReadOnlyList<PyDict> Flags(OneZeroResult? result) => result is null ? [] : OneZeroResultTrees.Facts(result).Flags ?? [];

    private static PyDict ReconciliationView(OneZeroResult pp, OneZeroResult mm)
    {
        var report = Reconciliation.Reconcile(pp, mm);
        return Dict(("annual_average_diff", report.AnnualAverageDiff), ("unit_diff_count", report.Units.Count(r => Num(r, "max_abs_diff") > 0)),
            ("donut_hole_employee_count", report.EmployeeWeeksDonutHole.Count), ("eligibility_disagreement_count", report.EligibilityDisagreements.Count),
            ("invariant_holds", report.InvariantHolds), ("invariant_violation_count", report.InvariantViolations.Count),
            ("invariant_violations", report.InvariantViolations), ("units", report.Units), ("donut_hole_top_10", report.EmployeeWeeksDonutHole.Take(10).ToList()));
    }

    private (PyDict View, PyDict Credit) EntityView(string code, OneZeroPack pack, PyDict feins, PyDict credit)
    {
        var treatment = pack.EntityCombination;
        var view = Dict(("treatment", treatment), ("_disc_ref", "DISC-4"), ("entity_count", feins.Count),
            ("entities", feins.Aggregate(new PyDict(), (result, pair) => result.Add(pair.Key, EntityName(pair.Key)))));
        if (treatment == "prohibited")
        {
            var combined = library.CombineEntityCredits(code, feins);
            foreach (var (fein, row) in (PyDict)combined["per_fein"]!)
            {
                ((PyDict)row!).Set("entity_name", EntityName(fein));
            }

            foreach (var field in new[] { "per_fein", "combined_annual_credit_usd", "combined_lifetime_credit_usd" })
            {
                view.Set(field, combined[field]);
            }

            credit.Set("annual_credit_usd", combined["combined_annual_credit_usd"]).Set("lifetime_credit_usd", combined["combined_lifetime_credit_usd"])
                .Set("qualifying_jobs", combined["combined_qualifying_jobs"]).Set("_entity_combination", "prohibited");
        }
        var note = treatment == "prohibited"
            ? "Entities cannot be combined for this program (DISC-4); credit is computed per FEIN with the statutory threshold applied to each, then summed."
            : feins.Count > 1
                ? $"{feins.Count} legal entities in this state; combination is '{treatment}' (pending DISC-4), so they are tested together on the combined state Average Headcount. Under a 'prohibited' state each entity would be tested against the threshold on its own."
                : $"Single legal entity in this state; combination is '{treatment}' (pending DISC-4). Credit computed on the state Average Headcount.";
        return (view.Set("note", note), credit);
    }

    private static string EntityName(string fein) => fein switch
    {
        "58-2233445" => "MeridianCore Distribution GA, Inc.",
        "58-1234567" or "13-7654321" or "57-2345678" or "75-3456789" or "56-4567890" or "62-5678901"
            or "59-6789012" or "31-7890123" or "84-8901234" or "54-9012345" => "MeridianCore Logistics LLC",
        _ => fein
    };
}
