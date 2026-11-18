using System.Globalization;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Payroll;
using TaxCredit.Infrastructure.Sources.Cache;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources;

/// <summary>SQL-served logical lakehouse payroll and its catalogue share the certified Domain port.</summary>
/// <remarks>
/// With a <see cref="ClientProjectionCache"/> a client's projection is reused until its stamp (source fingerprint plus pay-code lookup
/// digest) changes or the version-check window lapses; without one (the default) every read goes to the source exactly as before.
/// </remarks>
public sealed class SqlClientSource(SourceScanner scanner, PayrollProjector projector, FiscalRuleAdapter fiscal,
    FootprintGuard? guard = null, SourceLimits? limits = null, ClientProjectionCache? cache = null)
    : IClientPayrollSource, ISourceReader, ISourceCatalogue, IPayrollFreshness
{
    private int _freshScopes;
    /// <inheritdoc />
    public long? FixtureAccountId => null;
    /// <inheritdoc />
    public bool IsConfigured => scanner.IsConfigured;
    /// <summary>Explicit reset: payroll aggregates, and the projection cache when one is on. With the cache off payroll rows are not cached.</summary>
    public void ClearCache()
    {
        scanner.ClearCache();
        cache?.Clear();
    }
    /// <summary>Controls and optional-table absence for the selected client, null only for an unknown account.</summary>
    public PayrollProjection? LoadProjection(long accountId) => cache is null ? LoadUncached(accountId)
        : cache.GetOrLoad(new ProjectionKey(accountId, projector.CacheIdentity), Volatile.Read(ref _freshScopes) > 0,
            () => Stamp(accountId), () => LoadUncached(accountId));
    /// <inheritdoc />
    public IDisposable RequireFresh()
    {
        if (cache is null) { return NoPayrollFreshness.Instance.RequireFresh(); }
        Interlocked.Increment(ref _freshScopes);
        return new FreshScope(this);
    }
    private PayrollProjection? LoadUncached(long accountId) =>
        new SourceDatasetReader(scanner).Load(accountId) is { } dataset ? projector.Project(dataset) : null;
    /// <summary>The comparison value: the cheap source marker plus what the operator's lookups would do to the same rows.</summary>
    private string Stamp(long accountId) =>
        new SourceFingerprintReader(scanner).Fingerprint(accountId).Sha256 + "|" + projector.LookupDigest(accountId);
    private sealed class FreshScope(SqlClientSource owner) : IDisposable
    {
        private int _open = 1;
        public void Dispose()
        {
            if (Interlocked.Exchange(ref _open, 0) == 1) { Interlocked.Decrement(ref owner._freshScopes); }
        }
    }
    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) =>
        accountId is { } id ? LoadProjection(id)?.Rows ?? [] : [];
    /// <inheritdoc />
    /// <remarks>
    /// Refuses with <see cref="SourcePortfolioTooLarge"/> before holding more than the configured number of clients or
    /// rows. Each account's size is read from the cheap scope aggregate before its payroll is, never after.
    /// </remarks>
    public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods()
    {
        var bound = limits ?? SourceLimits.Default;
        var accounts = ListAccounts();
        if (accounts.Count > bound.PortfolioMaxAccounts) { throw SourcePortfolioTooLarge.ForAccounts(accounts.Count, bound.PortfolioMaxAccounts); }
        var result = new Dictionary<long, IReadOnlyList<PayRow>>();
        long running = 0;
        foreach (var account in accounts)
        {
            running += PayrollScope(account.AccountId).TotalRows;
            if (running > bound.PortfolioMaxRows) { throw SourcePortfolioTooLarge.ForRows(running, bound.PortfolioMaxRows); }
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
    public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => Footprint(ListAccounts().Select(a => a.AccountId).ToArray());
    /// <inheritdoc />
    public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint(IReadOnlyCollection<long> accountIds)
    {
        ArgumentNullException.ThrowIfNull(accountIds);
        if (accountIds.Count == 0) { return new Dictionary<long, IReadOnlyList<string>>(); }
        var queries = new SourceQueries(scanner);
        var timeout = guard?.Admit(() => RowEstimate(queries));
        var states = new Dictionary<long, SortedSet<string>>();
        try
        {
            foreach (var query in queries.Footprint(accountIds, timeout))
            {
                foreach (var row in scanner.ReadAggregate(query))
                {
                    var id = SourceValues.Id(row, "account_id")!.Value;
                    if (!states.TryGetValue(id, out var held)) { states[id] = held = new SortedSet<string>(StringComparer.Ordinal); }
                    var state = SourceValues.Text(row, "work_state");
                    if (state.Length > 0) { held.Add(state); }
                }
            }
        }
        catch (SourceTimedOut) when (guard is not null)
        {
            guard.RememberTimeout();
            throw FootprintGuard.TimedOut(timeout ?? guard.TimeoutSeconds);
        }
        return states.ToDictionary(p => p.Key, p => (IReadOnlyList<string>)p.Value.ToArray());
    }

    /// <summary>The catalogue's payroll row count; an endpoint that cannot answer simply has no estimate.</summary>
    private long? RowEstimate(SourceQueries queries)
    {
        try
        {
            var row = scanner.ReadAggregate(queries.RowEstimate(guard?.TimeoutSeconds)).FirstOrDefault();
            return row is not null && row["rows"] is { } value && Convert.ToInt64(value, CultureInfo.InvariantCulture) is > 0 and var rows ? rows : null;
        }
        catch (SourceFailureException) { return null; }
    }
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
    public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint(IReadOnlyCollection<long> accountIds)
    {
        ArgumentNullException.ThrowIfNull(accountIds);
        return fixtureAccountId is { } id && accountIds.Contains(id) ? Footprint() : new Dictionary<long, IReadOnlyList<string>>();
    }
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
