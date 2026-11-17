using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Ports.Sources;

/// <summary>The richer source port extends, rather than replaces, the certified engine's payroll seam.</summary>
public interface IClientPayrollSource : IPayrollSource
{
    /// <summary>The fixture's only tenant, or null for a multi-tenant source.</summary>
    long? FixtureAccountId { get; }
    /// <summary>Loads all held tenants, preserving source order within each tenant.</summary>
    IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods();
    /// <summary>Resolves a fiscal window without stripping its provenance.</summary>
    FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention);
    /// <summary>A program/state window, or null when no authored convention exists.</summary>
    FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear);
    /// <summary>The same resolver for callers needing only dates.</summary>
    (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear);
}

/// <summary>Client book and payroll footprint; unconfigured is not an empty configured book.</summary>
public interface ISourceReader
{
    /// <summary>Whether reads can be attempted.</summary>
    bool IsConfigured { get; }
    /// <summary>Source accounts, not claims or generated identities.</summary>
    IReadOnlyList<SourceAccount> ListAccounts();
    /// <summary>States per held client, never attributed dollars.</summary>
    IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint();
}

/// <summary>Read-side aggregates over the same projected population.</summary>
public interface ISourceCatalogue
{
    /// <summary>Distinct years/dates/states and unfiltered projected row count.</summary>
    PayrollScope PayrollScope(long accountId);
    /// <summary>A bounded connection lifetime for a synchronous group of reads.</summary>
    IDisposable SharedScope();
}

/// <summary>An observed source marker, deliberately not a Delta commit identifier.</summary>
public interface ISourceFingerprintReader
{
    /// <summary>Fresh account count/max-modified observation; no previous value is substituted after failure.</summary>
    SourceFingerprint Fingerprint(long accountId);
}

/// <summary>Customer-neutral book shape; values are source data, not telemetry dimensions.</summary>
public sealed record SourceAccount(long AccountId, string Name, string? BillingState = null,
    long? IndustryTypeId = null, long? ActualNumberOfEmployees = null);

/// <summary>Scope derives tax-year labels from pay dates; statutory windows are resolved separately.</summary>
public sealed record PayrollScope(long TotalRows, IReadOnlyList<long> TaxYears,
    IReadOnlyList<string> States, IReadOnlyList<string> PayDates);

/// <summary>Deterministic encoding identifies an observation, not a reproducible historical snapshot.</summary>
public sealed record SourceFingerprint(string Kind, long RowCount, string? MaximumModified,
    string ModifiedStatus, string Encoding, string Sha256, string Provenance,
    IReadOnlyList<string> Limitations);

/// <summary>Narrow read bridge for Persistence's lookup store; implementations must propagate read failures.</summary>
public interface ISourceLookupReader
{
    /// <summary>Returns active candidates for the client and global client 0 only. The resolver checks scope again.</summary>
    IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId);
}

/// <summary>Provider data needed for precedence and effective-date checks, without storage or audit operations.</summary>
public sealed record SourceLookupEntry(string Lookup, long ClientId, string Kind, string Key, string Value,
    bool Inferred = false, DateOnly? EffectiveFrom = null, DateOnly? EffectiveTo = null);

/// <summary>Safe typed failure for host error mapping; upstream messages/configuration are never retained.</summary>
public abstract class SourceFailureException(string code, string dependency, string remedy) : Exception(code)
{
    /// <summary>A stable machine-readable refusal code.</summary>
    public string Code { get; } = code;
    /// <summary>The logical dependency, not its endpoint.</summary>
    public string Dependency { get; } = dependency;
    /// <summary>Operator guidance free of credentials and customer configuration.</summary>
    public string Remedy { get; } = remedy;
}

/// <summary>Non-finite payroll cannot enter the certified numeric model (FZ-04).</summary>
public sealed class UnsupportedNonfinitePayroll()
    : SourceFailureException("unsupported_nonfinite_payroll", "source_projection", "Supply finite payroll numbers; FZ-04 is outside the certified numeric model.");

/// <summary>Only classified transport failures permit opt-in fiscal fallback.</summary>
public sealed class SourceUnavailable(string dependency = "source_sql")
    : SourceFailureException("source_unavailable", dependency, "Restore the source connection or configure an approved offline fiscal fallback.");

/// <summary>No connection can be attempted, distinct from unknown account and empty payroll.</summary>
public sealed class SourceNotConfigured()
    : SourceFailureException("source_not_configured", "source_sql", "Configure the source analytics connection.");

/// <summary>A rejected generated statement is not an outage and must not enable fiscal fixture fallback.</summary>
public sealed class SourceQueryRejected()
    : SourceFailureException("source_query_rejected", "source_sql", "Correct the source query or adapter before retrying.");

/// <summary>Required metadata is absent, not a transient outage.</summary>
public sealed class SourceSchemaMismatch(string table, IReadOnlyList<string> missing)
    : SourceFailureException("source_schema_mismatch", "source_schema", "Validate the configured source mapping and schema.")
{
    /// <summary>The logical table only.</summary>
    public string Table { get; } = table;
    /// <summary>Missing logical fields.</summary>
    public IReadOnlyList<string> Missing { get; } = missing;
}

/// <summary>An absent table, tolerated only for explicitly optional dimensions.</summary>
public sealed class SourceTableMissing(string table)
    : SourceFailureException("source_table_missing", "source_schema", "Supply the required logical source table.")
{
    /// <summary>The logical table.</summary>
    public string Table { get; } = table;
}

/// <summary>Strict fiscal policy refuses assumption, including malformed/unrepresentable rules.</summary>
public sealed class FiscalRulesMissing()
    : SourceFailureException("fiscal_rules_missing", "lookup:entity_fiscal_year_rules", "Author a fiscal rule or explicitly select FISCAL_RULES_POLICY=assume.");

/// <summary>Strict pay-code policy refuses unauthored mappings, without exposing code text in errors.</summary>
public sealed class UnmappedPayCodes(long rows, int distinct)
    : SourceFailureException("unmapped_pay_codes", "lookup:pay_code_category", "Author pay-code mappings or review PAY_CODE_POLICY.")
{
    /// <summary>Payroll rows affected.</summary>
    public long Rows { get; } = rows;
    /// <summary>Distinct source codes affected.</summary>
    public int Distinct { get; } = distinct;
}

/// <summary>Stops streaming at the configured row ceiling rather than after materializing the account.</summary>
public sealed class SourceTooLarge(long limit)
    : SourceFailureException("account_too_large", "source_sql", "Review the account row limit before retrying.")
{
    /// <summary>The refused ceiling.</summary>
    public long Limit { get; } = limit;
}
