using System.Globalization;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Payroll;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources;

/// <summary>SQL-served logical lakehouse payroll and its catalogue share the certified Domain port.</summary>
public sealed class SqlClientSource(SourceScanner scanner, PayrollProjector projector, FiscalRuleAdapter fiscal)
    : IClientPayrollSource, ISourceReader, ISourceCatalogue
{
    /// <inheritdoc />
    public long? FixtureAccountId => null;
    /// <inheritdoc />
    public bool IsConfigured => scanner.IsConfigured;
    /// <summary>Explicit metadata reset; payroll aggregates and payroll rows are deliberately not cached.</summary>
    public void ClearCache() => scanner.ClearCache();
    /// <summary>Controls and optional-table absence for the selected client, null only for an unknown account.</summary>
    public PayrollProjection? LoadProjection(long accountId) =>
        new SourceDatasetReader(scanner).Load(accountId) is { } dataset ? projector.Project(dataset) : null;
    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) =>
        accountId is { } id ? LoadProjection(id)?.Rows ?? [] : [];
    /// <inheritdoc />
    public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods()
    {
        var result = new Dictionary<long, IReadOnlyList<PayRow>>();
        foreach (var account in ListAccounts())
        {
            var rows = LoadPayPeriods(account.AccountId);
            if (rows.Count > 0) { result.Add(account.AccountId, rows); }
        }
        return result;
    }
    /// <inheritdoc />
    public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) =>
        fiscal.ClientFiscalWindow(accountId, taxYear, convention);
    /// <inheritdoc />
    public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) =>
        fiscal.FiscalWindowForStateYear(accountId, state, taxYear);
    /// <inheritdoc />
    public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
        fiscal.WindowForStateYear(accountId, state, taxYear);
    /// <inheritdoc />
    public IReadOnlyList<SourceAccount> ListAccounts() => scanner.Scan("Account").Select(r =>
        new SourceAccount(SourceValues.Id(r, "account_id") ?? throw new SourceSchemaMismatch("Account", ["account_id"]),
            SourceValues.Text(r, "name"), SourceValues.Get(r, "billing_state") as string,
            SourceValues.Id(r, "industry_type_id"), SourceValues.Id(r, "actual_number_of_employees"))).ToArray();
    /// <inheritdoc />
    public PayrollScope PayrollScope(long accountId)
    {
        var rows = scanner.ReadAggregate(new SourceQueries(scanner).Scope(accountId)).ToArray();
        return new PayrollScope(rows.Sum(r => Convert.ToInt64(r["rows_in"], CultureInfo.InvariantCulture)),
            rows.Select(r => SourceValues.Id(r, "tax_year")).OfType<long>().Distinct().Order().ToArray(),
            rows.Select(r => SourceValues.Text(r, "work_state")).Where(s => s.Length > 0).Distinct().Order(StringComparer.Ordinal).ToArray(),
            rows.Select(r => SourceValues.Date(r, "pay_date")).OfType<DateOnly>().Distinct().Order()
                .Select(d => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)).ToArray());
    }
    /// <inheritdoc />
    public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() =>
        scanner.ReadAggregate(new SourceQueries(scanner).Footprint())
            .GroupBy(r => SourceValues.Id(r, "account_id")!.Value).ToDictionary(g => g.Key,
                g => (IReadOnlyList<string>)g.Select(r => SourceValues.Text(r, "work_state"))
                    .Where(s => s.Length > 0).Distinct().Order(StringComparer.Ordinal).ToArray());
    /// <inheritdoc />
    public IDisposable SharedScope() => scanner.SharedScope();
}

/// <summary>CSV bridge reuses the certified parser/converter by project reference; it never opens an analytics connection.</summary>
public sealed class CsvClientSource(string path, long? fixtureAccountId, FiscalRuleAdapter fiscal)
    : IClientPayrollSource, ISourceReader, ISourceCatalogue
{
    private readonly CsvPayrollSource _csv = new(path, fixtureAccountId);
    /// <inheritdoc />
    public long? FixtureAccountId => fixtureAccountId;
    /// <inheritdoc />
    public bool IsConfigured => File.Exists(path);
    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => _csv.LoadPayPeriods(accountId);
    /// <inheritdoc />
    public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods()
    {
        var rows = LoadPayPeriods(null);
        return fixtureAccountId is { } id && rows.Count > 0
            ? new Dictionary<long, IReadOnlyList<PayRow>> { [id] = rows } : new Dictionary<long, IReadOnlyList<PayRow>>();
    }
    /// <inheritdoc />
    public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) =>
        fiscal.ClientFiscalWindow(accountId, taxYear, convention);
    /// <inheritdoc />
    public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) =>
        fiscal.FiscalWindowForStateYear(accountId, state, taxYear);
    /// <inheritdoc />
    public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
        fiscal.WindowForStateYear(accountId, state, taxYear);
    /// <inheritdoc />
    public IReadOnlyList<SourceAccount> ListAccounts() =>
        IsConfigured && fixtureAccountId is { } id ? [new SourceAccount(id, "Reference Dataset Client")] : [];
    /// <inheritdoc />
    public PayrollScope PayrollScope(long accountId) => SourceScope.FromRows(LoadPayPeriods(accountId));
    /// <inheritdoc />
    public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => fixtureAccountId is { } id && IsConfigured
        ? new Dictionary<long, IReadOnlyList<string>> { [id] = PayrollScope(id).States }
        : new Dictionary<long, IReadOnlyList<string>>();
    /// <inheritdoc />
    public IDisposable SharedScope() => EmptyScope.Instance;
}

/// <summary>CSV/materialized callers use the same scope meaning as SQL aggregates.</summary>
public static class SourceScope
{
    /// <summary>Only already-projected rows contribute; no certified computation is rerun.</summary>
    public static PayrollScope FromRows(IReadOnlyList<PayRow> rows) => new(rows.Count,
        rows.Select(r => SourceValues.ParseIdentifier(r.Get("Tax_Year"), "Tax_Year") ?? throw new SourceSchemaMismatch("Payroll", ["Tax_Year"]))
            .Distinct().Order().ToArray(),
        PayrollRows.StatesPresent(rows), rows.Select(r => r.PayDateText()).Where(d => d.Length > 0).Distinct()
            .Order(StringComparer.Ordinal).ToArray());
}

internal sealed class EmptyScope : IDisposable
{
    internal static EmptyScope Instance { get; } = new();
    public void Dispose() { }
}
