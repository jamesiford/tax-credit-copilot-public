using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

internal static class GoldQueryCatalog
{
    internal static IReadOnlyList<GoldQueryDataset> Datasets => Model.Value;
    private static readonly Lazy<IReadOnlyList<GoldQueryDataset>> Model = new(() => Array.AsReadOnly(new[]
    {
        Dataset("unit_year_master", "is_current", false, true, GoldValues.UnitColumns.Where(c => c is not "client_id" and not "is_current")),
        Dataset("unit_credit_installment", "is_current", false, true, ["worksite_id", "program_code", "method", "creation_year", "tax_year",
            "tranche_jobs", "jobs_maintained", "per_job_usd", "claimable_usd", "projected", "run_id", "appended_at"]),
        Dataset("unit_month_summary", "live_run", false, true, ["tax_year", "method", "run_id", "worksite_id", .. GoldValues.Months,
            "total", "average_headcount", "months_with_headcount", "unreachable_months"]),
        Dataset("run_method_summary", "live_run", false, true, ["tax_year", "method", "run_id", "program_code", "annual_average",
            "eligible_employees", "employees_evaluated", "matrix_rows", "unit_fein_rows", "contested_months", "month_ends", "appended_at"]),
        Dataset("employee_period_fact", "live_run", true, false, ["tax_year", "run_id", "employee_id", "record_token", "worksite_id",
            "entity_fein", "job_title", "pay_period_start", "pay_period_end", "pay_date", "period_days", "pay_frequency_code", "hours",
            "wages", "pay_code", "included", "selection_decision", "qc_flag"]),
        Dataset("employee_eligibility", "live_run", true, true, ["tax_year", "method", "run_id", "employee_id", "record_token",
            "total_hours", "total_wages", "first_start", "last_end", "days", "weeks_worked", "avg_weekly_hours", "avg_weekly_wages", "eligible", "weight"]),
        Dataset("onezero_matrix", "live_run", true, true, ["tax_year", "method", "run_id", "employee_id", "record_token",
            "worksite_id", "entity_fein", "first_pps", "last_ppe", "weight", .. GoldValues.Months]),
        Dataset("run_manifest", "none", false, false, ["run_id", "tax_year", "program_code", "fiscal_year_begin", "fiscal_year_end",
            "step1_assumption_set_id", "onezero_assumption_set_id", "rule_pack_version", "code_commit", "calculation_id",
            "run_started_at", "run_completed_at", "run_status", "superseded_by_run_id", "triggered_by"]),
    }));

    private static readonly HashSet<string> IntegerColumns = ["tax_year", "creation_year", "months_reachable", "months_with_headcount", "tranche_years",
        "eligible_employees", "employees_evaluated", "matrix_rows", "unit_fein_rows", "contested_months", "period_days", "days"];
    private static readonly HashSet<string> DecimalColumns = ["average_headcount", "base_average_headcount", "net_new_vs_base", "threshold",
        "eligible_jobs", "new_jobs_created", "high_water_mark", "per_job_usd", "annual_credit_usd", "claimable_usd", "tranche_jobs",
        "jobs_maintained", "total", "annual_average", "hours", "wages", "total_hours", "total_wages", "weeks_worked", "avg_weekly_hours",
        "avg_weekly_wages", "weight", .. GoldValues.Months];
    private static readonly HashSet<string> BoolColumns = ["is_base_year", "year_complete", "declined", "qualified", "backfilled",
        "base_year_overridden", "high_water_mark_overridden", "projected", "included", "eligible"];
    private static readonly HashSet<string> DateColumns = ["first_start", "last_end", "first_pps", "last_ppe", "pay_period_start",
        "pay_period_end", "pay_date", "fiscal_year_begin", "fiscal_year_end"];
    private static readonly HashSet<string> FreeText = ["decline_reason", "designation", "job_title", "pay_code"];
    private static readonly HashSet<string> EmployeeMeasures = ["hours", "wages", "total_hours", "total_wages", "avg_weekly_hours", "avg_weekly_wages"];
    private static readonly HashSet<string> Money = ["per_job_usd", "annual_credit_usd", "claimable_usd", "wages", "total_wages", "avg_weekly_wages"];

    private static GoldQueryDataset Dataset(string name, string currency, bool employees, bool method, IEnumerable<string> names) =>
        new(name, currency, employees, method, Array.AsReadOnly(names.Select(n => Column(n, employees, name == "onezero_matrix", name == "run_manifest")).ToArray()));

    private static GoldQueryColumn Column(string name, bool employee, bool matrix, bool manifest)
    {
        var blocked = name is "employee_id" or "triggered_by";
        var type = IntegerColumns.Contains(name) ? "int" : DecimalColumns.Contains(name) ? "decimal" :
            BoolColumns.Contains(name) ? "bool" : DateColumns.Contains(name) ? "date" :
            name is "appended_at" or "run_started_at" or "run_completed_at" ? "datetime" : "text";
        var role = blocked || name is "record_token" or "run_id" ? "identifier" :
            type == "bool" ? "flag" : (type is "int" or "decimal") && name is not "tax_year" and not "creation_year" ? "measure" : "dimension";
        var sensitivity = blocked ? "blocked" :
            employee && (name == "record_token" || EmployeeMeasures.Contains(name) || (matrix && name.StartsWith("month_", StringComparison.Ordinal)))
                ? "employee_level" : "public_aggregate";
        string[] aggs = blocked ? [] : role == "measure" ? ["count", "count_distinct", "sum", "avg", "min", "max"] :
            role == "flag" ? ["count", "sum"] : type is "int" or "decimal" or "date" or "datetime" ?
            ["count", "count_distinct", "min", "max"] : ["count", "count_distinct"];
        string[] ops = blocked || name is "month_ends" or "unreachable_months" || (name == "run_id" && !manifest) ? [] :
            type == "bool" ? ["eq"] : type is "int" or "decimal" or "date" or "datetime" ? ["eq", "in", "between", "gte", "lte"] :
            FreeText.Contains(name) ? ["eq", "in", "contains"] : ["eq", "in"];
        return new GoldQueryColumn(name, type, role, sensitivity, Array.AsReadOnly(aggs), Array.AsReadOnly(ops), Money.Contains(name) ? "USD" : null);
    }
}
