using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

public sealed partial class GoldReader
{
    private static (string Where, object?[] Values) UnitWhere(string method, int? year, string? program, string alias = "")
    {
        var prefix = alias.Length == 0 ? "" : alias + ".";
        var values = new List<object?> { method };
        var where = "{tenant" + (alias.Length == 0 ? "" : ":" + alias) + "} AND " +
            prefix + "is_current = 1 AND " + prefix + "method = ?";
        if (year is not null)
        {
            where += " AND " + prefix + "tax_year = ?";
            values.Add(year);
        }
        if (!string.IsNullOrEmpty(program))
        {
            where += " AND " + prefix + "program_code = ?";
            values.Add(program);
        }
        return (where, values.ToArray());
    }

    /// <inheritdoc />
    public GoldRowsPage UnitYears(long clientId, string method, int? taxYear = null, string? programCode = null, int limit = 25, int offset = 0)
    {
        var (where, values) = UnitWhere(method, taxYear, programCode, "m");
        var total = One(clientId, "SELECT COUNT(*) AS count_rows FROM tcc_gold.unit_year_master m WHERE " + where, values)!;
        var selected = string.Join(", ", GoldValues.UnitColumns.Select(c => "m." + c));
        var items = Many(clientId, Page($"SELECT {selected}, s.months_with_headcount, s.unreachable_months " +
            "FROM tcc_gold.unit_year_master m LEFT JOIN tcc_gold.unit_month_summary s " +
            "ON s.client_id = m.client_id AND s.tax_year = m.tax_year AND s.method = m.method " +
            "AND s.worksite_id = m.worksite_id AND s.run_id = m.run_id WHERE " + where +
            " ORDER BY m.worksite_id, m.tax_year", limit, offset), values);
        return new GoldRowsPage(items, GoldValues.Int(total, "count_rows"));
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?>? Unit(long clientId, string worksiteId, int taxYear, string method, string? programCode = null)
    {
        var (where, values) = UnitWhere(method, taxYear, programCode);
        return One(clientId, Page("SELECT " + string.Join(", ", GoldValues.UnitColumns) +
            " FROM tcc_gold.unit_year_master WHERE " + where + " AND worksite_id = ? ORDER BY worksite_id", 1), [.. values, worksiteId]);
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?>? UnitMonths(long clientId, string worksiteId, int taxYear, string method, string runId) =>
        One(clientId, Page("SELECT * FROM tcc_gold.unit_month_summary WHERE {tenant} AND worksite_id = ? " +
            "AND tax_year = ? AND method = ? AND run_id = ? ORDER BY worksite_id", 1), worksiteId, taxYear, method, runId);

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> MonthSummaries(long clientId, string method, string runId, int? taxYear = null)
    {
        var sql = "SELECT * FROM tcc_gold.unit_month_summary WHERE {tenant} AND method = ? AND run_id = ?";
        object?[] values = [method, runId];
        if (taxYear is not null)
        {
            sql += " AND tax_year = ?";
            values = [.. values, taxYear];
        }
        return Many(clientId, sql + " ORDER BY worksite_id, tax_year", values);
    }

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Installments(long clientId, string method, string? programCode = null)
    {
        var (where, values) = UnitWhere(method, null, programCode);
        return Many(clientId, "SELECT * FROM tcc_gold.unit_credit_installment WHERE " + where +
            " ORDER BY worksite_id, creation_year, tax_year", values);
    }

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> CreditColumns(long clientId, string method, string? programCode = null)
    {
        var (where, values) = UnitWhere(method, null, programCode);
        return Many(clientId, $"SELECT worksite_id, tax_year, {Sum("claimable_usd")} AS claimable_usd, " +
            "MAX(CAST(projected AS INT)) AS projected, MIN(creation_year) AS creation_year " +
            "FROM tcc_gold.unit_credit_installment WHERE " + where +
            " GROUP BY worksite_id, tax_year ORDER BY worksite_id, tax_year", values);
    }

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitTotals(long clientId, string method, string? programCode = null)
    {
        var (where, values) = UnitWhere(method, null, programCode);
        var totals = Many(clientId, $"SELECT worksite_id, {Sum("annual_credit_usd")} AS total_annual_credit_usd, " +
            "MAX(high_water_mark) AS final_high_water_mark FROM tcc_gold.unit_year_master WHERE " +
            where + " GROUP BY worksite_id ORDER BY worksite_id", values);
        var lifetime = Many(clientId, $"SELECT worksite_id, {Sum("claimable_usd")} AS total_tranche_lifetime_usd " +
            "FROM tcc_gold.unit_credit_installment WHERE " + where + " GROUP BY worksite_id", values)
            .ToDictionary(r => GoldValues.Text(r, "worksite_id"), r => r["total_tranche_lifetime_usd"], StringComparer.Ordinal);
        foreach (var row in totals.Cast<Dictionary<string, object?>>())
        {
            row["total_tranche_lifetime_usd"] = lifetime.GetValueOrDefault(GoldValues.Text(row, "worksite_id"));
        }
        return totals;
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?> UnitPage(long clientId, string method, int? taxYear = null, string? programCode = null, int limit = 25, int offset = 0)
    {
        using var scope = Scope();
        var run = LatestRun(clientId, programCode);
        var result = new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["run"] = run,
            ["in_flight"] = RunInFlight(clientId),
            ["items"] = GoldValues.EmptyRows,
            ["total"] = 0,
            ["months"] = GoldValues.EmptyRows,
            ["installments"] = GoldValues.EmptyRows,
            ["unit_totals"] = GoldValues.EmptyRows,
        };
        if (run is null)
        {
            return result;
        }
        var page = UnitYears(clientId, method, taxYear, programCode, limit, offset);
        var months = taxYear is null ? PageMonths(clientId, method, page.Items) :
            MonthSummaries(clientId, method, GoldValues.Text(run, "run_id"), taxYear);
        var totals = UnitTotals(clientId, method, programCode);
        if (taxYear is null)
        {
            var keys = page.Items.Select(r => (GoldValues.Text(r, "worksite_id"), GoldValues.Int(r, "tax_year"))).ToHashSet();
            var sites = keys.Select(k => k.Item1).ToHashSet(StringComparer.Ordinal);
            totals = totals.Where(r => sites.Contains(GoldValues.Text(r, "worksite_id"))).ToArray();
        }
        result["items"] = page.Items;
        result["total"] = taxYear is null && page.Items.Count == 0 ? 0 : page.Total;
        result["months"] = months;
        result["installments"] = CreditColumns(clientId, method, programCode);
        result["unit_totals"] = totals;
        return result;
    }
}
