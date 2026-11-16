using System.Globalization;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

internal static class TrendDisclosures
{
    internal static List<object?> Build(OrderedMap<long, PyDict> meta, IReadOnlyList<PyDict> units)
    {
        var output = new List<object?>
        {
            Disclosure("DISC-8", "base year", "The frozen base year and its high-water-mark treatment are read from a verbal SME description and are not yet confirmed against the Georgia Job Tax Credit form."),
            Disclosure("DISC-10", "tier", "Tier designations are prototype data covering four worksites. Units outside that registry are shown unassigned and fall back to the rule pack's minimum-new-jobs threshold."),
            Disclosure("TIER-FLAT", "credit amount", "Claimable dollars use one statutory amount per qualifying job. Tier-varied amounts are not authored in any rule pack, so a Tier 2 location is priced at the Tier 1 rate."),
        };
        if (Varies(meta, "threshold") || Varies(meta, "per_job_usd"))
        {
            output.Add(Disclosure("STATUTE-DRIFT", "threshold", "The minimum-new-jobs threshold or per-job amount changed across this window. The tranche engine applies a single value; per-year statute is shown on each row."));
        }
        if (units.Any(u => PortfolioValues.Text(u, "census_tract").Length == 0))
        {
            output.Add(Disclosure("NO-TRACT", "census tract", "Census tract is not held anywhere in the system and is left blank."));
        }
        var unreachable = meta.Where(p => ((List<object?>)p.Value["unreachable_months"]!).Count > 0).OrderBy(p => p.Key).ToList();
        if (unreachable.Count > 0)
        {
            var named = string.Join(", ", unreachable.Select(p => Name(p.Key, (List<object?>)p.Value["unreachable_months"]!)));
            output.Add(Disclosure("NO-MEASURING-DATE", "month coverage", $"No pay period reaches the measuring date in {named}. Those months read zero as a fact about the pay calendar, not about headcount, and are marked rather than counted as a decline."));
        }
        return output;
    }

    private static bool Varies(OrderedMap<long, PyDict> meta, string key) =>
        meta.Select(p => PyRound.Round(PortfolioValues.Number(PortfolioValues.Dict(p.Value, "benefit"), key), 2)).Distinct().Skip(1).Any();

    private static string Name(long year, List<object?> months) =>
        "TY" + year.ToString(CultureInfo.InvariantCulture) + (months.Count > 1 ? " months " : " month ")
        + string.Join("/", months.Select(m => (PortfolioValues.Integer(m) + 1).ToString(CultureInfo.InvariantCulture)));

    private static PyDict Disclosure(string code, string subject, string text) =>
        new PyDict().Add("code", code).Add("subject", subject).Add("text", text);
}
