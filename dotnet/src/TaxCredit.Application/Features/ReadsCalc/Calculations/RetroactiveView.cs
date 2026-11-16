using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private PyDict Retroactive(ReadArguments args)
    {
        var all = Rows(args, true);
        var years = all.GroupBy(r => (long)DateOnly.ParseExact(r.PayDateText(), "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture).Year)
            .Where(group => group.Count() >= 200).Select(group => group.Key).Order().ToList();
        var payroll = new PayrollRows(library, defaults);
        var declined = payroll.UnauthoredStateYears(years);
        var averages = new Dictionary<(string Code, long Year), double>();
        foreach (var year in years)
        {
            foreach (var item in payroll.IterStatePacks(FiscalRows(all, year), year, onUnauthored: "skip").Where(item => item.Rows.Count >= 50))
            {
                averages[(item.ProgramCode, year)] = Run(item.Rows, year, item.Pack).AnnualAverage;
            }
        }

        var opportunities = new List<PyDict>();
        foreach (var ((code, year), average) in averages)
        {
            var state = defaults.ProgramState(code);
            var prior = averages.GetValueOrDefault((code, year - 1));
            var credit = library.ApplyOneZeroStateCredit(code, average, prior, null);
            if (Num(credit, "annual_credit_usd") <= 0)
            {
                continue;
            }

            var filed = code == defaults.ProgramCodeForState(state) && LegacyClaimExists(state, year);
            opportunities.Add(Select(credit, "credit_code", "credit_name", "citation", "qualifying_jobs", "annual_credit_usd", "lifetime_credit_usd")
                .Set("tax_year", year).Set("state", state).Set("program_code", code).Set("average_headcount", average)
                .Set("prior_year_average_headcount", prior).Set("already_filed", filed).Set("status", filed ? "filed" : "unclaimed_retroactive"));
        }
        var unclaimed = opportunities.Where(row => !ReadValues.Bool(row["already_filed"])).ToList();
        return Dict(("as_of", Today), ("tax_years_scanned", years.Where(year => !declined.ContainsKey(year.ToString(System.Globalization.CultureInfo.InvariantCulture))).ToList()),
            ("declined_years", declined.Select(pair =>
            {
                var states = (PyDict)pair.Value!;
                return Dict(("tax_year", long.Parse(pair.Key, System.Globalization.CultureInfo.InvariantCulture)), ("states", states.Keys.Order(StringComparer.Ordinal).ToList()),
                    ("reason", "no_authored_statute"), ("detail", states.First().Value));
            }).ToList()),
            ("opportunities", opportunities.OrderByDescending(row => Num(row, "lifetime_credit_usd")).ToList()),
            ("summary", Dict(("total_opportunities", opportunities.Count), ("unclaimed_count", unclaimed.Count),
                ("total_unclaimed_lifetime_usd", unclaimed.Sum(row => Num(row, "lifetime_credit_usd"))), ("declined_year_count", declined.Count))),
            ("tranche_analysis", RetroactiveTranches(averages)));
    }

    private List<PyDict> RetroactiveTranches(Dictionary<(string Code, long Year), double> averages)
    {
        var results = new List<PyDict>();
        foreach (var group in averages.GroupBy(pair => pair.Key.Code).OrderBy(group => group.Key, StringComparer.Ordinal))
        {
            if (group.Count() < 2)
            {
                continue;
            }

            var yearly = new OrderedMap<long, PyNumber>();
            foreach (var pair in group)
            {
                yearly.Set(pair.Key.Year, PyNumber.OfFloat(pair.Value));
            }

            var credit = library.ApplyOneZeroStateCredit(group.Key, group.MaxBy(pair => pair.Key.Year).Value);
            var rate = Num(credit, "amount_per_job_usd");
            if (rate <= 0)
            {
                continue;
            }

            var settings = new BaseYearSettings(PyNumber.OfFloat(Num(credit, "threshold")), PyNumber.OfFloat(rate));
            results.Add(BaseYearEngine.ComputeBaseYearTranches(defaults.ProgramState(group.Key), yearly, group.Min(pair => pair.Key.Year), settings).ToDict());
        }
        return results;
    }

    // The legacy scan's filing comparison uses this illustrative registry, not the operational Claims lifecycle.
    private static bool LegacyClaimExists(string state, long year) =>
        (state, year) is ("GA", 2024) or ("SC", 2025) or ("US", 2025) or ("TN", 2025) or ("VA", 2026);
}
