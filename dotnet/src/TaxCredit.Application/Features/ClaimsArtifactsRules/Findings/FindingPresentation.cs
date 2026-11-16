using System.Globalization;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

internal static class FindingPresentation
{
    private const string TwosTitle = "Employee counted at two worksites in one month";
    private const string TwosWhy = "The engine counts headcount per unit, so a person appearing at two worksites in the same month is counted twice. That inflates Average Headcount, which inflates the credit.";
    private const string PeriodWhy = "A period with almost no hours or wages still adds weeks to the denominator, which lowers the weekly average and can push someone below a statutory floor they actually clear. Whether such periods count is one policy question, not one question per period.";

    internal static IReadOnlyList<PyDict> Items(string kind, IReadOnlyList<PyDict> anomalies, long year, string? state,
        IReadOnlyDictionary<string, FindingResolution> decisions)
    {
        if (kind == "meaningful_pay_period")
        {
            return [Item(Id(kind, year, state), kind, "policy", "Pay periods too small to be real periods", PeriodWhy,
                "drop", "Excludes every period below the threshold from the denominator.", null, Population(anomalies), Evidence(kind), decisions)];
        }
        var result = new List<PyDict>();
        var clear = anomalies.Where(a => !Ambiguous(a)).ToArray();
        var split = anomalies.Where(Ambiguous).ToArray();
        if (clear.Length > 0)
        {
            result.Add(Item(Id(kind, year, state), kind, "policy", TwosTitle + " \u2014 clear-cut",
                TwosWhy + " In these one worksite holds at least 75% of the month's hours, so which unit owns the head is arithmetic rather than a judgement.",
                "assign", "Counts each employee at their dominant worksite for that month.", null,
                Population(clear).Add("dominance_threshold", .75), Evidence(kind), decisions));
        }
        if (split.Length > 25)
        {
            result.Add(Item(Id(kind + "_split", year, state), kind, "policy", TwosTitle + " \u2014 split evenly",
                TwosWhy + " In these the hours are split closely enough that no worksite obviously owns the head. There are too many to judge one at a time, which usually means it is a characteristic of this client's payroll rather than an anomaly \u2014 staff genuinely working across sites. Choose a tie-break rule.",
                "assign", "Counts each employee at whichever of their worksites holds the most hours that month, breaking ties on wages.",
                null, Population(split).Add("instance_cap", 25L), Evidence(kind), decisions));
        }
        else
        {
            result.AddRange(split.Select(a => Item($"t2:{a["employee_id"]}:{a["month"]}", kind, "instance",
                TwosTitle + " \u2014 split evenly", TwosWhy + " Here the hours are split closely enough that no worksite obviously owns the head, so this one needs a person.",
                "assign", "Counts the employee at their dominant worksite for that month.", a["employee_id"], null, a, decisions)));
        }
        return result;
    }

    private static string Id(string kind, long year, string? state) => $"policy:{kind}:{(string.IsNullOrEmpty(state) ? "ALL" : state)}:{year}";
    private static PyDict Evidence(string kind) => new PyDict().Add("type", kind).Add("units", Array.Empty<object>());
    private static PyDict[] Units(PyDict anomaly) => anomaly.TryGetValue("units", out var value) && value is IEnumerable<object?> units
        ? units.Cast<PyDict>().ToArray() : [];
    private static double Amount(PyDict value, string key) => value.TryGetValue(key, out var item) && item is not null
        ? Convert.ToDouble(item, CultureInfo.InvariantCulture) : 0;
    private static bool Ambiguous(PyDict anomaly)
    {
        var hours = Units(anomaly).Select(u => Amount(u, "hours")).ToArray();
        var total = PySum.Sum(hours);
        return total <= 0 || hours.Length == 0 || hours.Max() / total < .75;
    }

    private static PyDict Population(IReadOnlyList<PyDict> anomalies)
    {
        double wages = 0, hours = 0;
        foreach (var anomaly in anomalies)
        {
            var units = Units(anomaly);
            wages += units.Length > 0 ? PySum.Sum(units.Select(u => Amount(u, "wages")).ToArray()) : Amount(anomaly, "wages");
            hours += units.Length > 0 ? PySum.Sum(units.Select(u => Amount(u, "hours")).ToArray()) : Amount(anomaly, "hours");
        }
        return new PyDict().Add("instances", anomalies.Count)
            .Add("employees_affected", anomalies.Select(a => a["employee_id"]).Where(e => e is not (null or "")).Distinct().Count())
            .Add("total_wages", PyRound.Round(wages, 2)).Add("total_hours", PyRound.Round(hours, 2))
            .Add("sample", anomalies.Take(5).ToArray()).Add("sample_of", anomalies.Count);
    }

    private static PyDict Item(string id, string kind, string grain, string title, string why, string proposes,
        string effect, object? employee, PyDict? population, PyDict evidence, IReadOnlyDictionary<string, FindingResolution> decisions)
    {
        var decision = decisions.GetValueOrDefault(id);
        return new PyDict().Add("finding_id", id).Add("kind", kind).Add("grain", grain).Add("title", title)
            .Add("why_it_matters", why).Add("proposes", proposes).Add("proposed_effect", effect).Add("employee_id", employee)
            .Add("population", population).Add("evidence", evidence).Add("resolution", decision?.ToDict()).Add("requires_decision", decision is null);
    }
}
