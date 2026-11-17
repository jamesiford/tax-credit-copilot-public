using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>The client brief an agent can only narrate (Python <c>coverage.situation</c>).</summary>
public static class CoverageSituation
{
    private sealed class OrderComparer : IComparer<(long Rank, double NegIdentified, long TaxYear)>
    {
        public int Compare((long Rank, double NegIdentified, long TaxYear) x, (long Rank, double NegIdentified, long TaxYear) y)
        {
            var byRank = x.Rank.CompareTo(y.Rank);
            if (byRank != 0)
            {
                return byRank;
            }

            var byMoney = PySort.FloatComparer.Compare(x.NegIdentified, y.NegIdentified);
            return byMoney != 0 ? byMoney : x.TaxYear.CompareTo(y.TaxYear);
        }
    }

    /// <summary>
    /// Python <c>situation(claims)</c>: why you would call this client. Ordered by priority band, then identified dollars
    /// descending, then tax year; the money ordering uses <c>-float(identified)</c>, so two decimals that share a double compare
    /// equal and fall through to the year (a quirk mirrored as is). Money is a string throughout.
    /// </summary>
    /// <param name="claims">One client's cells.</param>
    /// <returns>An ordered tree: counts, programmes, years, the lead cell, <c>by_band</c>, three money totals and the unverified flag.</returns>
    public static PyDict Situation(IReadOnlyList<ProgramClaim> claims)
    {
        ArgumentNullException.ThrowIfNull(claims);
        var ranked = PySort.Sorted(claims, c => (c.PriorityBand.Rank(), -c.IdentifiedUsd.ToDouble(), c.TaxYear), new OrderComparer());
        var byBand = new PyDict();
        foreach (var claim in ranked)
        {
            var band = claim.PriorityBand.Value();
            if (!byBand.TryGetValue(band, out var entries))
            {
                byBand.Set(band, entries = new List<object?>());
            }

            ((List<object?>)entries!).Add(Cell(claim));
        }

        var lead = ranked.Count > 0 ? ranked[0] : null;
        var totals = Coverage.Totals(claims);
        return new PyDict()
            .Add("cells", (long)claims.Count)
            .Add("programs", PySort.Sorted(claims.Select(c => c.ProgramCode).Distinct(StringComparer.Ordinal), s => s, PyStr.Comparer).Cast<object?>().ToList())
            .Add("tax_years", claims.Select(c => c.TaxYear).Distinct().Order().Cast<object?>().ToList())
            .Add("lead_band", lead?.PriorityBand.Value())
            .Add("lead_program", lead?.ProgramCode)
            .Add("lead_tax_year", lead?.TaxYear)
            .Add("by_band", byBand)
            .Add("identified_usd", totals["identified_usd"])
            .Add("opportunity_usd", totals["opportunity_usd"])
            .Add("exposure_usd", totals["exposure_usd"])
            // The claimed side of the book is seeded; narrating "they under-claimed by $X" without this would assert an unsupplied filing.
            .Add("claimed_is_unverified", claims.Any(c => !c.Provenance.Verified()));
    }

    private static PyDict Cell(ProgramClaim claim) => new PyDict()
        .Add("program_code", claim.ProgramCode)
        .Add("tax_year", claim.TaxYear)
        .Add("identified_usd", claim.IdentifiedUsd.ToString())
        .Add("claimed_usd", claim.ClaimedUsd.ToString())
        .Add("opportunity_usd", claim.OpportunityUsd.ToString())
        .Add("net_new_jobs", claim.NetNewJobs)
        .Add("threshold_jobs", claim.ThresholdJobs)
        .Add("jobs_margin", claim.JobsMargin)
        .Add("outcome", claim.Outcome.Value())
        .Add("provenance_verified", claim.Provenance.Verified());
}
