namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;

internal static class PackageColumns
{
    internal static readonly string[] Names = ["Coverage", "Locations", "Installments", "Provenance", "Disclaimer"];
    internal static readonly string[] Coverage = ["program_code", "tax_year", "status", "provenance", "provenance_verified",
        "identified_usd", "claimed_usd", "certified_usd", "outcome", "is_base_year", "average_headcount",
        "base_average_headcount", "threshold_jobs", "identified_run_id", "rule_pack_version"];
    internal static readonly string[] Locations = ["method", "worksite_id", "program_code", "tax_year", "status", "average_headcount",
        "is_base_year", "base_average_headcount", "base_year_source", "net_new_vs_base", "months_reachable", "year_complete",
        "threshold", "threshold_source", "qualified", "tier", "designation", "tier_source", "eligible_jobs", "new_jobs_created",
        "high_water_mark", "per_job_usd", "tranche_years", "annual_credit_usd", "run_id"];
    internal static readonly string[] Installments = ["method", "worksite_id", "program_code", "creation_year", "tax_year",
        "tranche_jobs", "jobs_maintained", "per_job_usd", "claimable_usd", "projected", "run_id"];
    internal static readonly string[] Provenance = ["run_id", "program_code", "tax_year", "fiscal_year_begin", "fiscal_year_end",
        "rule_pack_version", "step1_assumption_set_id", "onezero_assumption_set_id", "code_commit", "calculation_id",
        "run_started_at", "run_completed_at"];
    internal static readonly string[] Disclaimer = [
        "Tax Credit Copilot claim package (v1).",
        "Every figure was computed by the deterministic calculation engine from payroll, under the rule pack and assumption sets named on the Provenance sheet. No figure was produced by a language model.",
        "Claimed amounts marked client_asserted or inherited rest on an unverified assertion; any variance computed against them is only as reliable as that assertion.",
        "The workbook is at location grain. It contains no employee identifiers, names or tax ids.",
        "This is not tax advice. A return must be prepared and reviewed by a qualified professional."
    ];
}
