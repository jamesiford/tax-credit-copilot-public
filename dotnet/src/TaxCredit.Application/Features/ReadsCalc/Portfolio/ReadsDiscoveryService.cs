using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

/// <summary>Discovery is a filtered view of the same statutory portfolio, never a second credit calculator.</summary>
/// <param name="portfolio">The scoped source-backed portfolio builder.</param>
public sealed class ReadsDiscoveryService(ReadsPortfolioService portfolio)
{
    /// <summary>Exclusion narrows hits, not the list of considered packs or the underlying calculation.</summary>
    public PyDict DiscoverCredits(IReadOnlyList<string>? excludeCodes = null, long? accountId = null, long? taxYear = null)
    {
        var year = taxYear ?? portfolio.LatestTaxYear(accountId: accountId);
        var result = FromTiles(portfolio.BuildPortfolio(year, accountId: accountId), excludeCodes);
        Record(year, result);
        return result;
    }

    /// <summary>Lets a sibling reuse already-built tiles rather than loading payroll again.</summary>
    public static PyDict FromTiles(IReadOnlyList<PyDict> tiles, IReadOnlyList<string>? excludeCodes = null)
    {
        ArgumentNullException.ThrowIfNull(tiles);
        var excluded = (excludeCodes ?? []).ToHashSet(StringComparer.Ordinal);
        var hits = tiles.Where(t => !excluded.Contains(PortfolioValues.Text(t, "code"))
                && PortfolioValues.Text(t, "basis") != "no_pack" && PortfolioValues.Number(t, "lifetime_credit_usd") > 0)
            .OrderByDescending(t => PortfolioValues.Integer(t["lifetime_credit_usd"])).Select(Hit).ToList();
        return new PyDict().Add("hits", PortfolioValues.List(hits))
            .Add("packs_considered", PortfolioValues.List(tiles.Select(t => t["code"])))
            .Add("excluded", PortfolioValues.List(excluded.Order(PyStr.Comparer)))
            .Add("totals", new PyDict().Add("hit_count", (long)hits.Count)
                .Add("annual_credit_usd", hits.Aggregate(System.Numerics.BigInteger.Zero, (sum, h) => sum + PortfolioValues.Integer(h["annual_credit_usd"])))
                .Add("lifetime_credit_usd", hits.Aggregate(System.Numerics.BigInteger.Zero, (sum, h) => sum + PortfolioValues.Integer(h["lifetime_credit_usd"]))));
    }

    private static PyDict Hit(PyDict tile) => new PyDict()
        .Add("credit_code", tile["code"]).Add("credit_name", tile["name"])
        .Add("jurisdiction", tile["jurisdiction"]).Add("citation", tile["citation"])
        .Add("qualifying_jobs", tile["qualifying_jobs"]).Add("basis", tile["basis"])
        .Add("annual_credit_usd", tile["annual_credit_usd"]).Add("benefit_period_years", tile["benefit_period_years"])
        .Add("lifetime_credit_usd", tile["lifetime_credit_usd"]);

    private static void Record(long year, PyDict result)
    {
        var recorder = TrailContext.Current;
        if (recorder is null)
        {
            return;
        }
        if (recorder.Title is "" or "Pending")
        {
            recorder.Title = "Credit Discovery";
        }
        if (recorder.Citation.Length == 0)
        {
            recorder.Citation = "multiple rule packs";
        }
        var hits = ((List<object?>)result["hits"]!).Cast<PyDict>().ToList();
        recorder.Record("Scan rule library (statutory One/Zero engine)",
            new PyDict().Add("tax_year", year).Add("packs_considered", result["packs_considered"]).Add("excluded", result["excluded"]),
            "build statutory portfolio; keep jurisdictions with lifetime_credit > 0 and not excluded",
            new PyDict().Add("hit_count", (long)hits.Count), "rule packs in backend/rules/ + tools/portfolio.py");
        foreach (var hit in hits)
        {
            recorder.Record("Hit: " + PortfolioValues.Text(hit, "credit_code"),
                new PyDict().Add("jurisdiction", hit["jurisdiction"]).Add("qualifying_jobs", hit["qualifying_jobs"]).Add("basis", hit["basis"]),
                "qualifying_jobs * per_job (or pct_of_wages) * benefit_period_years",
                new PyDict().Add("lifetime_credit_usd", hit["lifetime_credit_usd"]).Add("annual_credit_usd", hit["annual_credit_usd"]),
                PortfolioValues.Text(hit, "citation"));
        }
    }
}
