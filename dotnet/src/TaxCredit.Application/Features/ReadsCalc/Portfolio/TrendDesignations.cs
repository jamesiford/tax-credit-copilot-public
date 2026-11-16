using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

internal static class TrendDesignations
{
    internal static PyDict? At(DesignationRegistry registry, string unitId, long year, long? clientId)
    {
        var stored = registry.DesignationAt(unitId, year, clientId);
        if (stored is not null || clientId is not null || year < 2021
            || unitId is not ("GA_ATL_HQ" or "GA_SAV_DC" or "GA_MAC_OPS" or "GA_CUM_OPS"))
        {
            return stored;
        }
        // W1 supplies client-keyed timelines but omitted this existing, display-only legacy fixture registry.
        var tierTwo = unitId == "GA_MAC_OPS" && year < 2025;
        return new PyDict().Add("year", year >= 2025 ? 2025L : 2021L).Add("tier", tierTwo ? 2L : 1L)
            .Add("designation", tierTwo ? "Tier 2 — Less Developed Census Tract" : "Tier 1 — Standard")
            .Add("min_new_jobs", tierTwo ? 10L : 2L);
    }
}
