using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

/// <summary>Gold-only capability briefs: no source port or engine is available to these reads.</summary>
/// <param name="gold">The host's accepted-results reader.</param>
public sealed partial class ReadsStoredPortfolioBriefs(IGoldReadPort gold)
{
    /// <summary>Names absent calculation and prior-year coverage without inventing a zero current average.</summary>
    public PyDict ClientContext(long accountId, int taxYear, string method = "pay_period", string? programCode = null,
        Action<IReadOnlyDictionary<string, object?>>? onRun = null)
    {
        PortfolioValues.ValidateMethod(method);
        using var scope = gold.Scope();
        var current = gold.HeadcountSeries(accountId, taxYear, method, programCode);
        if (current["run"] is not IReadOnlyDictionary<string, object?> run || current["annual_average"] is null)
        {
            return NotCalculated(accountId, taxYear);
        }
        onRun?.Invoke(run);
        var prior = gold.HeadcountSeries(accountId, taxYear - 1, method, programCode);
        return new PyDict().Add("calculated", true).Add("client_id", accountId).Add("tax_year", (long)taxYear)
            .Add("method", method).Add("current_average", PortfolioValues.Number(current["annual_average"]))
            .Add("prior_average", PortfolioValues.Number(prior["annual_average"])).Add("has_prior_year", prior["annual_average"] is not null)
            .Add("month_ends", current["month_ends"]).Add("run_id", run.GetValueOrDefault("run_id"))
            .Add("produced_at", PortfolioValues.DisplayValue(run.GetValueOrDefault("produced_at")));
    }

    /// <summary>Judges every reached year after the base; no year after the base means null, not a negative verdict.</summary>
    public PyDict ClientTrend(long accountId, string method = "pay_period", string? programCode = null,
        Action<IReadOnlyDictionary<string, object?>>? onRun = null)
    {
        PortfolioValues.ValidateMethod(method);
        var series = gold.ClientYearSeries(accountId, method, programCode);
        if (series.GetValueOrDefault("run") is IReadOnlyDictionary<string, object?> run)
        {
            onRun?.Invoke(run);
        }
        var years = ((IEnumerable<IReadOnlyDictionary<string, object?>>)series["years"]!).ToList();
        if (years.Count == 0)
        {
            return new PyDict().Add("calculated", false).Add("client_id", accountId).Add("method", method);
        }
        var baseline = years.FirstOrDefault(y => y.GetValueOrDefault("is_base_year") is true);
        var afterBase = years.Where(y => baseline is null
            || PortfolioValues.Integer(y["tax_year"]) > PortfolioValues.Integer(baseline["tax_year"])).ToList();
        return new PyDict().Add("calculated", true).Add("client_id", accountId).Add("method", method)
            .Add("base_tax_year", baseline?.GetValueOrDefault("tax_year")).Add("years", PortfolioValues.List(years.Select(PortfolioValues.Tree)))
            .Add("years_held", (long)years.Count).Add("years_after_base", (long)afterBase.Count)
            .Add("eligible_every_year_since_base", afterBase.Count > 0 ? afterBase.All(y => PortfolioValues.Number(y["eligible_employees"]) > 0) : null)
            .Add("years_with_no_eligible_employees", PortfolioValues.List(afterBase.Where(y => PortfolioValues.Number(y["eligible_employees"]) == 0).Select(y => y["tax_year"])))
            .Add("note", "Years absent from this list were not reached by the run. They carry no figure, which is not the same as a zero. Where `eligible_every_year_since_base` is null there is no year after the base year to judge — say so rather than reporting a verdict.");
    }

    private static PyDict NotCalculated(long clientId, int year) =>
        new PyDict().Add("calculated", false).Add("client_id", clientId).Add("tax_year", (long)year);
}
