using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

internal static class GoldValidation
{
    internal static int Section9QueryCount => Queries.Count;

    internal static IReadOnlyList<(string Query, long RowCount)> Check(SqlSession session, string? publishingRun = null)
    {
        var failures = new List<(string Query, long RowCount)>();
        foreach (var (name, sql) in Queries)
        {
            var rows = session.QueryExempt(SqlExemption.Validation, sql);
            if (rows.Count > 0)
            {
                failures.Add((name, rows.Count));
            }
        }

        foreach (var table in new[] { "employee_period_fact", "employee_eligibility", "onezero_matrix", "run_method_summary", "unit_year_master", "unit_credit_installment" })
        {
            var rows = session.QueryExempt(SqlExemption.Validation, "SELECT DISTINCT g.run_id FROM tcc_gold." + table
                + " g LEFT JOIN tcc_ops.run_manifest r ON r.run_id=g.run_id AND r.client_id=g.client_id WHERE r.run_id IS NULL");
            if (rows.Count > 0)
            {
                failures.Add(("9.7 no orphaned run references: " + table, rows.Count));
            }
        }

        var duplicateManifests = session.QueryExempt(SqlExemption.Validation,
            "SELECT client_id FROM tcc_ops.run_manifest WHERE run_status='success' GROUP BY client_id,program_code HAVING COUNT(*)>1");
        if (duplicateManifests.Count > 0)
        {
            failures.Add(("9.11 one successful manifest per client-program", duplicateManifests.Count));
        }

        foreach (var table in new[] { "unit_year_master", "unit_credit_installment" })
        {
            var rows = session.QueryExempt(SqlExemption.Validation, "SELECT g.client_id FROM tcc_gold." + table
                + " g JOIN tcc_ops.run_manifest r ON r.client_id=g.client_id AND r.run_id=g.run_id WHERE g.is_current=1"
                + " AND (r.program_code<>g.program_code OR (r.run_status<>'success' AND r.run_id<>?))", publishingRun ?? string.Empty);
            if (rows.Count > 0)
            {
                failures.Add(("9.10 current rows have a usable manifest: " + table, rows.Count));
            }
        }

        return failures;
    }

    private static IReadOnlyList<(string Name, string Sql)> Queries { get; } =
    [
        ("9.1 one live claim per cell", "SELECT client_id FROM tcc_ops.program_claim WHERE effective_to IS NULL GROUP BY client_id,program_code,tax_year HAVING COUNT(*)>1"),
        ("9.2 one live engagement per client-program", "SELECT client_id FROM tcc_ops.program_engagement WHERE effective_to IS NULL GROUP BY client_id,program_code HAVING COUNT(*)>1"),
        ("9.3 one live resolution per finding", "SELECT client_id FROM tcc_ops.agent_finding_resolution WHERE superseded_at IS NULL GROUP BY client_id,finding_id HAVING COUNT(*)>1"),
        ("9.4 one current row per unit-year-method", "SELECT client_id FROM tcc_gold.unit_year_master WHERE is_current=1 GROUP BY client_id,worksite_id,program_code,method,tax_year HAVING COUNT(*)>1"),
        ("9.4b one current installment per window-year", "SELECT client_id FROM tcc_gold.unit_credit_installment WHERE is_current=1 GROUP BY client_id,worksite_id,program_code,method,creation_year,tax_year HAVING COUNT(*)>1"),
        ("9.4c installment arithmetic holds", "SELECT client_id FROM tcc_gold.unit_credit_installment WHERE is_current=1 AND (tax_year<creation_year OR CAST(jobs_maintained AS DECIMAL(19,4))>CAST(tranche_jobs AS DECIMAL(19,4)) OR ABS(CAST(claimable_usd AS DECIMAL(19,4))-ROUND(CAST(jobs_maintained AS DECIMAL(19,4))*CAST(per_job_usd AS DECIMAL(19,4)),0))>0.51)"),
        ("9.4d annual credit equals jobs x rate", "SELECT client_id FROM tcc_gold.unit_year_master WHERE is_current=1 AND eligible_jobs IS NOT NULL AND per_job_usd IS NOT NULL AND ABS(CAST(annual_credit_usd AS DECIMAL(19,4))-ROUND(CAST(eligible_jobs AS DECIMAL(19,4))*CAST(per_job_usd AS DECIMAL(19,4)),0))>0.51"),
        ("9.4e new jobs within net-new", "SELECT client_id FROM tcc_gold.unit_year_master WHERE is_current=1 AND CAST(new_jobs_created AS DECIMAL(19,4))>CAST(net_new_vs_base AS DECIMAL(19,4))+0.01"),
        ("9.5 declined claims carry a reason", "SELECT claim_id FROM tcc_ops.program_claim WHERE status='declined' AND (decline_reason IS NULL OR LTRIM(RTRIM(decline_reason))='')"),
        ("9.6a program_claim.status in domain", "SELECT DISTINCT status FROM tcc_ops.program_claim WHERE status NOT IN ('not_assessed','assessed','proposed','declined','claimed','certified','amended')"),
        ("9.6b program_claim.provenance in domain", "SELECT DISTINCT provenance FROM tcc_ops.program_claim WHERE provenance NOT IN ('computed','filed_by_us','client_asserted','inherited','authority_confirmed')"),
        ("9.6c program_engagement.scope in domain", "SELECT DISTINCT scope FROM tcc_ops.program_engagement WHERE scope NOT IN ('in_scope','out_of_scope','prospective')"),
        ("9.6d finding resolution in domain", "SELECT DISTINCT resolution FROM tcc_ops.agent_finding_resolution WHERE resolution NOT IN ('accept','assign','drop','flag')"),
        ("9.6e eligibility method in domain", "SELECT DISTINCT method FROM tcc_gold.employee_eligibility WHERE method NOT IN ('min_max','pay_period')"),
        ("9.6f unit_year_master.status in domain", "SELECT DISTINCT status FROM tcc_gold.unit_year_master WHERE status NOT IN ('base','above_minimum','below_minimum','partial','no_data','before_base','in_progress')"),
        ("9.6g threshold_source in domain", "SELECT DISTINCT threshold_source FROM tcc_gold.unit_year_master WHERE threshold_source IS NOT NULL AND threshold_source NOT IN ('designation','rule_pack')"),
        ("9.6h tier_source in domain", "SELECT DISTINCT tier_source FROM tcc_gold.unit_year_master WHERE tier_source IS NOT NULL AND tier_source NOT IN ('prototype','unassigned')"),
        ("9.7 no orphaned run references", "SELECT DISTINCT g.run_id FROM tcc_gold.unit_month_summary g LEFT JOIN tcc_ops.run_manifest r ON r.run_id=g.run_id AND r.client_id=g.client_id WHERE r.run_id IS NULL"),
        ("9.8 average headcount is total / 12", "SELECT client_id FROM tcc_gold.unit_month_summary WHERE ABS(CAST(average_headcount AS DECIMAL(19,4))-(CAST(total AS DECIMAL(19,4))/12.0))>0.01"),
        ("9.9 no model wrote a figure", "SELECT action_id FROM tcc_ops.agent_action_audit WHERE is_deterministic_path=0 AND run_id IS NOT NULL"),
    ];
}
