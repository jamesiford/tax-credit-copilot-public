using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

public sealed partial class ReadsPortfolioService
{
    private PyDict? FederalTile(long taxYear)
    {
        var pack = FederalPack();
        if (pack is null)
        {
            return null;
        }
        var hires = referenceData.CountFederalNewHires(taxYear);
        var benefit = PortfolioValues.Dict(pack, "benefit");
        var rate = PortfolioValues.Get(benefit, "wotc_target_group_qualification_rate") is { } value ? PortfolioValues.Number(value) : 1.0;
        var qualified = PyRound.RoundToInteger(hires * rate);
        var threshold = PortfolioValues.Number(PortfolioValues.Dict(pack, "thresholds"), "minimum_new_jobs");
        if ((double)qualified < threshold)
        {
            return null;
        }

        var perJob = PortfolioValues.Number(benefit, "amount_per_qualifying_job_usd");
        var years = PortfolioValues.Integer(benefit["benefit_period_years"]);
        var annual = PyRound.RoundToInteger((double)qualified * perJob);
        var credit = PortfolioValues.Dict(pack, "credit");
        var citation = PortfolioValues.Text(credit, "statutory_citation");
        return new PyDict().Add("code", credit["code"]).Add("name", credit["name"])
            .Add("jurisdiction", PortfolioValues.Dict(pack, "jurisdiction")["code"]).Add("citation", citation)
            .Add("basis", "new_hires_in_window").Add("metric_label", $"WOTC-eligible hires ({taxYear.ToString(CultureInfo.InvariantCulture)})")
            .Add("metric_value", qualified).Add("metric_sublabel", $"~{rate.ToString("P0", CultureInfo.InvariantCulture).Replace(" ", "", StringComparison.Ordinal)} of {hires.ToString(CultureInfo.InvariantCulture)} gross new hires (target-group certified)")
            .Add("qualifying_jobs", qualified).Add("threshold", threshold)
            .Add("per_job_label", "$" + perJob.ToString("#,0", CultureInfo.InvariantCulture) + " per hire")
            .Add("annual_credit_usd", annual).Add("lifetime_credit_usd", annual * years).Add("benefit_period_years", years)
            .Add("trend", PortfolioValues.List(Enumerable.Repeat(0.0, 12)))
            .Add("calculation_trail", FederalTrail(taxYear, hires, rate, qualified, (perJob, annual, years, citation)))
            .Add("filing", PortfolioValues.Get(pack, "filing") ?? DefaultFiling())
            .Add("why_surfaced", $"{hires.ToString(CultureInfo.InvariantCulture)} new hires in {taxYear.ToString(CultureInfo.InvariantCulture)}; ~{qualified.ToString(CultureInfo.InvariantCulture)} expected WOTC-certified "
                + $"at the illustrative {rate.ToString("P0", CultureInfo.InvariantCulture).Replace(" ", "", StringComparison.Ordinal)} target-group rate");
    }

    private PyDict? FederalPack()
    {
        try
        {
            return library.LoadPack("federal_wotc_lite.json");
        }
        catch (PyFileNotFoundError)
        {
            return null;
        }
    }

    private static List<object?> FederalTrail(long year, long hires, double rate, System.Numerics.BigInteger qualified,
        (double PerJob, System.Numerics.BigInteger Annual, System.Numerics.BigInteger Years, string Citation) values) =>
    [
        Step("Identify new hires in the federal window", new PyDict().Add("tax_year", year),
            "count employees with hire_date in tax_year (payroll.csv)", new PyDict().Add("gross_new_hires", hires),
            "synthetic payroll.csv hire_date; per-hire WOTC basis"),
        Step("Apply illustrative WOTC target-group certification rate",
            new PyDict().Add("gross_new_hires", hires).Add("target_group_rate", rate),
            "qualifying_hires = round(gross_new_hires * target_group_rate)", new PyDict().Add("qualifying_hires", qualified),
            "DOL ETA 9061/9062 target-group screening (illustrative rate; see pack)"),
        Step("Apply per-hire federal credit amount", new PyDict().Add("new_hires", qualified).Add("amount_per_hire_usd", values.PerJob),
            "new_hires * amount_per_hire_usd", new PyDict().Add("annual_credit_usd", values.Annual), values.Citation),
        Step($"Project over {values.Years.ToString(CultureInfo.InvariantCulture)}-year benefit period",
            new PyDict().Add("annual_credit_usd", values.Annual).Add("benefit_period_years", values.Years),
            "annual_credit_usd * benefit_period_years", new PyDict().Add("lifetime_credit_usd", values.Annual * values.Years), values.Citation),
    ];

    private PyDict NoPackTile(string state, int employeeCount) => new PyDict()
        .Add("code", state + "_NO_PACK").Add("name", state + ": no state rule pack in library").Add("jurisdiction", state)
        .Add("citation", "n/a — federal credits (WOTC) still apply").Add("basis", "no_pack")
        .Add("metric_label", "Eligible employees").Add("metric_value", (long)employeeCount)
        .Add("metric_sublabel", $"{employeeCount.ToString(CultureInfo.InvariantCulture)} {state} employees · no state JTC equivalent in library")
        .Add("qualifying_jobs", 0L).Add("threshold", 0L).Add("per_job_label", "—")
        .Add("annual_credit_usd", 0L).Add("lifetime_credit_usd", 0L).Add("benefit_period_years", 0L)
        .Add("trend", PortfolioValues.List(Enumerable.Repeat(0.0, 12)))
        .Add("calculation_trail", new List<object?> { Step("Look up state rule pack for " + state,
            new PyDict().Add("state", state).Add("library", PortfolioValues.List(library.StateToPack.SortedKeys())),
            "STATE_TO_PACK[state]", new PyDict().Add("pack", null).Add("fallback", "federal-only"), "backend/rules/") })
        .Add("filing", new PyDict().Add("window", "n/a — no state rule pack").Add("cycle", "federal-only"))
        .Add("why_surfaced", "No state rule pack for " + state + "; federal WOTC still applies");
}
