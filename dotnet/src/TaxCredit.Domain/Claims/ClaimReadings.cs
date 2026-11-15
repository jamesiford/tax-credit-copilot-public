using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>Claim readings that need a client's whole history rather than one cell.</summary>
public static class ClaimReadings
{
    /// <summary>
    /// Python <c>declining_reading(claims)</c>: whether a client's headcount is falling back toward its base year.
    /// Returns <c>null</c>, never a reading with <c>declining = false</c>: an absent trend and a flat one are different, and only
    /// one earns a band. It is NOT exposure (a forecast about a year nobody has filed is not a finding against a filed return),
    /// and it needs credit actually earned (<c>identified_usd &gt; 0</c>), because shrinking is only a problem if there is
    /// a credit to shrink out of. Compares the two most recent measured years only, so a recovered dip is history.
    /// </summary>
    /// <param name="claims">The client's cells, in any order.</param>
    /// <returns>The reading as an ordered tree, or <c>null</c> when there is nothing to say.</returns>
    public static PyDict? DecliningReading(IReadOnlyList<ProgramClaim> claims)
    {
        ArgumentNullException.ThrowIfNull(claims);
        var measured = PySort.Sorted(claims.Where(c => c.AverageHeadcount is not null && !c.IsBaseYear), c => c.TaxYear, Comparer<long>.Default);
        if (measured.Count < 2)
        {
            return null;
        }

        var latest = measured[^1];
        var prior = measured[^2];
        if (latest.AverageHeadcount >= prior.AverageHeadcount)
        {
            return null;
        }

        var earned = measured.Where(c => PyDecimalOps.Compare(c.IdentifiedUsd, PyDecimalOps.Zero) > 0).ToList();
        if (earned.Count == 0)
        {
            return null;
        }

        var peak = measured[0];
        foreach (var c in measured)
        {
            // max(key=...) keeps the FIRST maximum: a later claim replaces it only if strictly greater (NaN never does).
            if (c.AverageHeadcount > peak.AverageHeadcount)
            {
                peak = c;
            }
        }

        return new PyDict()
            .Add("declining", true)
            .Add("years_falling", YearsFalling(measured))
            .Add("peak_tax_year", peak.TaxYear)
            .Add("peak_average_headcount", peak.AverageHeadcount!.Value)
            .Add("latest_tax_year", latest.TaxYear)
            .Add("latest_average_headcount", latest.AverageHeadcount!.Value)
            .Add("fallen_by", PyRound.Round(peak.AverageHeadcount.Value - latest.AverageHeadcount.Value, 2))
            .Add("below_base", latest.BaseAverageHeadcount is not null && latest.AverageHeadcount < latest.BaseAverageHeadcount)
            .Add("credit_earned_usd", PyDecimalOps.Sum(earned.Select(c => c.IdentifiedUsd)).ToString())
            .Add("earned_tax_years", earned.Select(c => (object?)c.TaxYear).ToList());
    }

    /// <summary>How long it has been falling: consecutive year-on-year drops ending at the latest year.</summary>
    private static long YearsFalling(List<ProgramClaim> measured)
    {
        long consecutive = 0;
        for (var i = measured.Count - 1; i >= 1; i--)
        {
            if (measured[i].AverageHeadcount < measured[i - 1].AverageHeadcount)
            {
                consecutive++;
            }
            else
            {
                break;
            }
        }

        return consecutive;
    }
}
