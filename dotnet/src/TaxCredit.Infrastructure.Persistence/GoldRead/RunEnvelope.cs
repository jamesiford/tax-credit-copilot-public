namespace TaxCredit.Infrastructure.Persistence.GoldRead;

/// <summary>The canonical provenance envelope, including the distinction between an absent year and an unknown unit.</summary>
public static class RunEnvelope
{
    /// <summary>Preserves the run identity even when this requested year has no rows.</summary>
    public static IReadOnlyDictionary<string, object?> Create(IReadOnlyDictionary<string, object?>? run,
        IReadOnlyDictionary<string, object?>? inFlight, bool hasRows = true)
    {
        var calculated = run is not null && hasRows;
        Dictionary<string, object?>? provenance = null;
        if (run is not null)
        {
            provenance = new Dictionary<string, object?>(StringComparer.Ordinal);
            foreach (var key in new[] { "run_id", "calculation_id", "code_commit", "rule_pack_version",
                "step1_assumption_set_id", "onezero_assumption_set_id", "triggered_by", "tax_year", "program_code" })
            {
                provenance[key] = run[key];
            }
            provenance["produced_at"] = run["run_completed_at"];
            provenance["started_at"] = run["run_started_at"];
        }
        return new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["calculation_state"] = calculated ? "calculated" : "not_calculated",
            ["run"] = provenance,
            ["newer_run_in_flight"] = inFlight is not null,
            ["in_flight"] = inFlight,
            ["message"] = calculated ? null : "Not yet calculated. Run the calculation to see figures.",
        };
    }
}
