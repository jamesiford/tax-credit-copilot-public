using System.Globalization;
using System.Text.Json;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

internal static class GoldValues
{
    internal static readonly IReadOnlyList<IReadOnlyDictionary<string, object?>> EmptyRows = Array.Empty<IReadOnlyDictionary<string, object?>>();
    internal static readonly string[] Months = Enumerable.Range(1, 12).Select(i => $"month_{i:00}").ToArray();
    internal static readonly string[] UnitColumns = [
        "client_id", "worksite_id", "entity_fein", "program_code", "method", "tax_year",
        "average_headcount", "is_base_year", "base_average_headcount", "base_year_source",
        "net_new_vs_base", "months_reachable", "year_complete", "declined", "decline_reason",
        "threshold", "threshold_source", "qualified", "status", "tier", "designation", "tier_source",
        "eligible_jobs", "new_jobs_created", "high_water_mark", "backfilled", "per_job_usd",
        "tranche_years", "annual_credit_usd", "base_year_overridden", "high_water_mark_overridden",
        "run_id", "is_current", "appended_at"];
    private static readonly HashSet<string> Money = [
        "per_job_usd", "annual_credit_usd", "claimable_usd", "identified_usd", "claimed_usd",
        "certified_usd", "total_annual_credit_usd", "total_tranche_lifetime_usd"];
    private static readonly HashSet<string> Bits = [
        "is_base_year", "year_complete", "declined", "qualified", "backfilled", "base_year_overridden",
        "high_water_mark_overridden", "is_current", "eligible", "projected"];
    private static readonly HashSet<string> Numbers = [
        "average_headcount", "base_average_headcount", "net_new_vs_base", "threshold", "eligible_jobs",
        "new_jobs_created", "high_water_mark", "final_high_water_mark", "weight", "total",
        "annual_average", "avg_weekly_hours", "avg_weekly_wages", "weeks_worked", "total_hours",
        "total_wages", "hours", "wages", "mm_weeks", "mm_hours", "mm_wages", "pp_weeks",
        "pp_hours", "pp_wages", "month_total", "month_average_headcount", "tranche_jobs", "jobs_maintained", .. Months];

    internal static Dictionary<string, object?> Shape(IReadOnlyDictionary<string, object?> row) =>
        row.ToDictionary(p => p.Key, p => Value(p.Key, p.Value), StringComparer.Ordinal);

    private static object? Value(string name, object? value)
    {
        if (value is null or DBNull)
        {
            return null;
        }
        if (Money.Contains(name))
        {
            return Convert.ToString(value, CultureInfo.InvariantCulture);
        }
        if (Bits.Contains(name))
        {
            return Convert.ToInt32(value, CultureInfo.InvariantCulture) != 0;
        }
        if (Numbers.Contains(name) || value is decimal)
        {
            return Convert.ToDouble(value, CultureInfo.InvariantCulture);
        }
        if (name == "tier" && value is string tier && long.TryParse(tier, NumberStyles.Integer, CultureInfo.InvariantCulture, out var tierNumber))
        {
            return tierNumber;
        }
        return value is DateTime time ? time.ToString("yyyy-MM-ddTHH:mm:ss.FFFFFFF", CultureInfo.InvariantCulture) : value;
    }

    internal static double Number(IReadOnlyDictionary<string, object?> row, string key) =>
        row.TryGetValue(key, out var value) && value is not null ? Convert.ToDouble(value, CultureInfo.InvariantCulture) : 0;
    internal static int Int(IReadOnlyDictionary<string, object?> row, string key) => checked((int)Number(row, key));
    internal static string Text(IReadOnlyDictionary<string, object?> row, string key) =>
        row.TryGetValue(key, out var value) ? Convert.ToString(value, CultureInfo.InvariantCulture) ?? "" : "";
    internal static IReadOnlyList<string> MonthEnds(IReadOnlyDictionary<string, object?>? summary)
    {
        if (summary is null || !summary.TryGetValue("month_ends", out var value) || value is null)
        {
            return [];
        }
        try
        {
            return JsonSerializer.Deserialize<string[]>(Convert.ToString(value, CultureInfo.InvariantCulture)!) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }
}
