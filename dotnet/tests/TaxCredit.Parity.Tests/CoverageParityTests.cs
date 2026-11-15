using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS4 (coverage): replays every call of <c>parity/goldens/coverage.jsonl.gz</c> (production <c>domain/coverage.py</c> on
/// CPython 3.12) against <see cref="Coverage"/> and <see cref="CoverageSituation"/>, bit for bit.
/// </summary>
public sealed class CoverageParityTests
{
    private const string File = "coverage.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(File, Invoke, ["totals", "totals_by_program", "group_by_client", "situation", "matrix"], minimumCalls: 9000, minimumErrors: 0);

    [Fact]
    public void A_row_never_nets_an_opportunity_against_an_exposure()
    {
        // test_coverage_totals.py::TestARowNeverNets, kept as a plain-language statement of the rule the golden also pins.
        var opportunity = ProgramClaim.Create(new ClaimSpec { ClientId = 1001, ProgramCode = "GA_JTC", TaxYear = 2022, Status = ClaimStatus.Assessed, IdentifiedUsd = "40000", ClaimedUsd = "0", ClaimId = "a" });
        var exposure = ProgramClaim.Create(new ClaimSpec { ClientId = 1001, ProgramCode = "GA_JTC", TaxYear = 2023, Status = ClaimStatus.Claimed, IdentifiedUsd = "0", ClaimedUsd = "40000", ClaimId = "b" });
        var totals = Coverage.Totals([opportunity, exposure]);
        Assert.Equal("40000", totals["opportunity_usd"]);
        Assert.Equal("40000", totals["exposure_usd"]);
        Assert.Equal(1L, totals["exposure_cells"]);
        Assert.Empty(Coverage.TotalsByProgram([]));
    }

    private static object? Invoke(PyDict call)
    {
        var a = (PyDict)call["args"]!;
        var claims = ((List<object?>)a["claims"]!).Select(s => ProgramClaim.Create(ClaimGolden.Spec(s))).ToList();
        return (string)call["fn"]! switch
        {
            "totals" => Coverage.Totals(claims),
            "totals_by_program" => Coverage.TotalsByProgram(claims),
            "group_by_client" => Coverage.GroupByClient(claims).Select(g => (object?)new List<object?> { g.ClientId, g.Claims.Select(c => (object?)c.ClaimId).ToList() }).ToList(),
            "situation" => CoverageSituation.Situation(claims),
            "matrix" => Coverage.Matrix(claims, Engagements((PyDict)a["engagements"]!)).Cast<object?>().ToList(),
            _ => throw new PyUnsupportedException("unknown function " + call["fn"]),
        };
    }

    private static Dictionary<string, EngagementScope?> Engagements(PyDict raw) =>
        raw.ToDictionary(kv => kv.Key, kv => kv.Value is string s ? (EngagementScope?)ClaimEnumExtensions.ScopeFromValue(s) : null, StringComparer.Ordinal);
}
