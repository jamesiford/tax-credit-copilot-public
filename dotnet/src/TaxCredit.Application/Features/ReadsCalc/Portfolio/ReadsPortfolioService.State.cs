using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

public sealed partial class ReadsPortfolioService
{
    private PyDict? StateTile(IReadOnlyList<PayRow> current, IReadOnlyList<PayRow> prior,
        (string State, string Code, long Year, long EndMonth) scope)
    {
        var result = RunState(current, scope.State, scope.Code, scope.Year, scope.EndMonth);
        if (result is null)
        {
            return null;
        }
        var previous = RunState(prior, scope.State, scope.Code, scope.Year - 1, scope.EndMonth)?.AnnualAverage ?? 0.0;
        var credit = library.ApplyOneZeroStateCredit(scope.Code, result.AnnualAverage, previous, null);
        var pack = library.LoadPack(library.PackFileFor(scope.Code)!);
        var threshold = PortfolioValues.Number(PortfolioValues.Dict(pack, "thresholds"), "minimum_new_jobs");
        var netNew = PyRound.Round(Math.Max(0.0, result.AnnualAverage - previous), 2);
        var partTime = result.EligibleEmployees.Count(e => e.Weight < 1.0);
        return StateTileFields(credit, result, previous, threshold)
            .Add("net_new_headcount", netNew).Add("part_time_eligible_count", (long)partTime)
            .Add("trend", MonthlyTrend(result))
            .Add("calculation_trail", StateTrail(result, credit, (scope.State, scope.Year, previous, threshold, netNew, partTime)))
            .Add("filing", PortfolioValues.Get(pack, "filing") ?? DefaultFiling())
            .Add("why_surfaced", $"{PortfolioValues.Display(netNew)} net-new average headcount (current {PortfolioValues.Display(result.AnnualAverage)} vs prior {PortfolioValues.Display(previous)}) "
                + $"vs {threshold.ToString("0", CultureInfo.InvariantCulture)}-job threshold → {PortfolioValues.Display(PortfolioValues.Number(credit, "qualifying_jobs"))} qualifying");
    }

    private static PyDict StateTileFields(PyDict credit, OneZeroResult current, double previous, double threshold) => new PyDict()
        .Add("code", credit["credit_code"]).Add("name", credit["credit_name"])
        .Add("jurisdiction", credit["state"]).Add("citation", credit["citation"])
        .Add("basis", "net_new_headcount").Add("metric_label", "Avg monthly headcount")
        .Add("metric_value", current.AnnualAverage)
        .Add("metric_sublabel", $"Prior year {PortfolioValues.Display(previous)} · {current.EligibleEmployees.Count.ToString(CultureInfo.InvariantCulture)} eligible employees")
        .Add("qualifying_jobs", credit["qualifying_jobs"]).Add("threshold", threshold)
        .Add("per_job_label", "$" + PortfolioValues.Number(credit, "amount_per_job_usd").ToString("#,0", CultureInfo.InvariantCulture) + " per qualifying job")
        .Add("annual_credit_usd", credit["annual_credit_usd"]).Add("lifetime_credit_usd", credit["lifetime_credit_usd"])
        .Add("benefit_period_years", credit["benefit_period_years"]).Add("average_headcount", current.AnnualAverage)
        .Add("prior_year_average_headcount", previous);

    private static List<object?> MonthlyTrend(OneZeroResult result)
    {
        var months = new double[12];
        foreach (var unit in result.Summary)
        {
            for (var index = 0; index < Math.Min(12, unit.MonthTotals.Count); index++)
            {
                months[index] += unit.MonthTotals[index];
            }
        }
        return PortfolioValues.List(months.Select(m => PyRound.Round(m, 2)));
    }

    private static List<object?> StateTrail(OneZeroResult result, PyDict credit,
        (string State, long Year, double Prior, double Threshold, double NetNew, int PartTime) scope)
    {
        var citation = PortfolioValues.Text(credit, "citation");
        return [
            Step($"Run statutory One/Zero Base Calculation ({scope.State} {scope.Year.ToString(CultureInfo.InvariantCulture)})",
                new PyDict().Add("eligible_employees", (long)result.EligibleEmployees.Count).Add("part_time_half_weight", (long)scope.PartTime),
                "per-employee 1/0.5/0 by unit per month → Average Monthly Headcount = mean of 12 monthly unit counts",
                new PyDict().Add("average_headcount", result.AnnualAverage), citation),
            Step($"Net-new vs prior year ({(scope.Year - 1).ToString(CultureInfo.InvariantCulture)})",
                new PyDict().Add("current_avg_headcount", result.AnnualAverage).Add("prior_avg_headcount", scope.Prior),
                "net_new = max(0, current_avg_headcount - prior_avg_headcount)", new PyDict().Add("net_new", scope.NetNew), citation),
            Step($"Apply {scope.Threshold.ToString("0", CultureInfo.InvariantCulture)}-job statutory threshold",
                new PyDict().Add("net_new", scope.NetNew).Add("threshold", scope.Threshold),
                "qualifying_jobs = max(0, net_new - threshold)", new PyDict().Add("qualifying_jobs", credit["qualifying_jobs"]), citation),
            Step($"Apply benefit math ({credit["credit_name"]})",
                new PyDict().Add("qualifying_jobs", credit["qualifying_jobs"]).Add("amount_per_job_usd", PortfolioValues.Get(credit, "amount_per_job_usd")),
                "annual = qualifying_jobs * amount_per_job; lifetime = annual * benefit_years",
                new PyDict().Add("annual_credit_usd", credit["annual_credit_usd"]).Add("lifetime_credit_usd", credit["lifetime_credit_usd"]), citation),
        ];
    }

    private static PyDict Step(string step, PyDict inputs, string formula, PyDict output, string citation) =>
        new PyDict().Add("step", step).Add("inputs", inputs).Add("formula", formula).Add("output", output).Add("citation", citation);

    private static PyDict DefaultFiling() => new PyDict().Add("window", "See rule pack").Add("cycle", "unspecified");
}
