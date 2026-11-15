using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>
/// How a portfolio of claims reads (Python <c>domain/coverage.py</c>): totals, and what a cell means in context.
/// </summary>
/// <remarks>
/// Opportunity and exposure are summed separately at every level and never netted: netting would let a client we over-claimed for
/// cancel one we under-claimed for, and hide the exposure, which is the half with a deadline. Amounts are strings: they are exact
/// decimals, and a JSON number is a double.
/// </remarks>
public static class Coverage
{
    /// <summary>Python <c>totals(claims)</c>: money and counts over a set of cells.</summary>
    /// <param name="claims">The cells.</param>
    /// <returns>An ordered tree: three money strings, <c>opportunity_usd</c>, <c>exposure_usd</c>, then the counts.</returns>
    public static PyDict Totals(IReadOnlyList<ProgramClaim> claims)
    {
        ArgumentNullException.ThrowIfNull(claims);
        var opportunity = PyDecimalOps.Sum(claims.Select(c => c.OpportunityUsd));
        var exposure = PyDecimalOps.Sum(claims.Where(c => c.Outcome == Outcome.OverClaimed).Select(c => PyDecimalOps.Negate(c.VarianceUsd)));
        return new PyDict()
            .Add("identified_usd", PyDecimalOps.Sum(claims.Select(c => c.IdentifiedUsd)).ToString())
            .Add("claimed_usd", PyDecimalOps.Sum(claims.Select(c => c.ClaimedUsd)).ToString())
            .Add("opportunity_usd", opportunity.ToString())
            .Add("exposure_usd", exposure.ToString())
            .Add("cells", (long)claims.Count)
            .Add("exposure_cells", (long)claims.Count(c => c.IsExposure))
            .Add("unverified_cells", (long)claims.Count(c => !c.Provenance.Verified()));
    }

    /// <summary>
    /// Python <c>totals_by_program(claims)</c>: one total per programme, the account grid's row totals, summed here as decimals
    /// (the grid once reduced them as floats in the browser). Keys are in code-point order.
    /// </summary>
    /// <param name="claims">The cells.</param>
    /// <returns>Programme code to <see cref="Totals"/>; empty (not a zero row) for no claims.</returns>
    public static PyDict TotalsByProgram(IReadOnlyList<ProgramClaim> claims)
    {
        ArgumentNullException.ThrowIfNull(claims);
        var grouped = new Dictionary<string, List<ProgramClaim>>(StringComparer.Ordinal);
        foreach (var claim in claims)
        {
            if (!grouped.TryGetValue(claim.ProgramCode, out var rows))
            {
                grouped[claim.ProgramCode] = rows = [];
            }

            rows.Add(claim);
        }

        var result = new PyDict();
        foreach (var code in PySort.Sorted(grouped.Keys, k => k, PyStr.Comparer))
        {
            result.Add(code, Totals(grouped[code]));
        }

        return result;
    }

    /// <summary>
    /// Python <c>matrix(claims, engagements)</c>: cells, each carrying its own reading. A gap in a programme we are not engaged to
    /// fill is not an opportunity, so an unclaimed or unassessed cell there reads <c>out_of_scope</c>.
    /// </summary>
    /// <param name="claims">The cells.</param>
    /// <param name="engagements">Programme code (exact match) to scope; a missing or <c>null</c> entry means no engagement.</param>
    /// <returns>One wire dictionary per claim with <c>engagement_scope</c> appended.</returns>
    public static List<PyDict> Matrix(IReadOnlyList<ProgramClaim> claims, IReadOnlyDictionary<string, EngagementScope?> engagements)
    {
        ArgumentNullException.ThrowIfNull(claims);
        ArgumentNullException.ThrowIfNull(engagements);
        var cells = new List<PyDict>();
        foreach (var claim in claims)
        {
            var cell = claim.ToDict();
            var scope = engagements.TryGetValue(claim.ProgramCode, out var found) ? found : null;
            cell.Set("engagement_scope", scope?.Value());
            if (scope == EngagementScope.OutOfScope && claim.Outcome is Outcome.Unclaimed or Outcome.NotAssessed)
            {
                cell.Set("outcome", Outcome.OutOfScope.Value());
            }

            cells.Add(cell);
        }

        return cells;
    }

    /// <summary>
    /// Python <c>group_by_client(claims)</c>: partition by tenant, in first-seen order. Claims stay partitioned rather than
    /// concatenated so that summing across clients takes a deliberate act.
    /// </summary>
    /// <param name="claims">The cells.</param>
    /// <returns>Client ids in first-seen order with their cells in input order.</returns>
    public static List<(long ClientId, List<ProgramClaim> Claims)> GroupByClient(IReadOnlyList<ProgramClaim> claims)
    {
        ArgumentNullException.ThrowIfNull(claims);
        var groups = new List<(long ClientId, List<ProgramClaim> Claims)>();
        var index = new Dictionary<long, int>();
        foreach (var claim in claims)
        {
            if (!index.TryGetValue(claim.ClientId, out var at))
            {
                index[claim.ClientId] = at = groups.Count;
                groups.Add((claim.ClientId, []));
            }

            groups[at].Claims.Add(claim);
        }

        return groups;
    }
}
