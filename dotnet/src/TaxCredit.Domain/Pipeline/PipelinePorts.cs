using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

/// <summary>Where pay-period rows physically come from (Python <c>application/source_ports.PayrollSource.load_pay_periods</c>).</summary>
public interface IPayrollSource
{
    /// <summary>Python <c>load_pay_periods(account_id)</c>: a tenant's rows, empty for a tenant the source does not hold.</summary>
    /// <param name="accountId">The tenant; <c>null</c> keeps the source's default.</param>
    /// <returns>The rows, in source order.</returns>
    IReadOnlyList<PayRow> LoadPayPeriods(long? accountId);
}

/// <summary>One stored fiscal-year rule (Python's <c>EntityFiscalYearRules</c> row or an app-owned override): the attributes <c>_window_from_rule</c> reads.</summary>
/// <param name="Name">The rule's name; one starting <c>override:</c> is app-owned.</param>
/// <param name="RuleExpression">The source's expression, shown in the note when non-empty.</param>
/// <param name="FiscalYearBegin">A <see cref="DateOnly"/>, text starting with an ISO date, or <c>null</c>.</param>
/// <param name="FiscalYearEnd">A <see cref="DateOnly"/>, text starting with an ISO date, or <c>null</c>.</param>
public sealed record FiscalRule(string? Name, string? RuleExpression, object? FiscalYearBegin, object? FiscalYearEnd);

/// <summary>The reads <c>infrastructure/payroll/fiscal_source.py</c> performs that are I/O: which source is active and the client's stored rules.</summary>
public interface IFiscalRuleSource
{
    /// <summary>Python <c>active_data_source() == "lakehouse"</c>: only the lakehouse holds per-client fiscal rules.</summary>
    bool HoldsClientRules { get; }

    /// <summary>Python <c>_rules_with_overrides(account_id)</c>: the client's rules in provider order, <c>null</c> when none could be read or exist.</summary>
    /// <param name="accountId">The client.</param>
    /// <returns>The rules or <c>null</c>.</returns>
    IReadOnlyList<FiscalRule>? RulesWithOverrides(long accountId);
}

/// <summary>The fiscal rules of the CSV fixture source: it holds none, so every window is an assumed calendar year.</summary>
public sealed class NoFiscalRules : IFiscalRuleSource
{
    /// <inheritdoc />
    public bool HoldsClientRules => false;

    /// <inheritdoc />
    public IReadOnlyList<FiscalRule>? RulesWithOverrides(long accountId) => null;
}

/// <summary>Where a run's gold payload goes (Python <c>application/gold_ports.GoldWriter</c>; the warehouse adapter implements it).</summary>
public interface IGoldWriter
{
    /// <summary>Python <c>write_run(payload)</c>.</summary>
    /// <param name="payload">Everything one run writes.</param>
    /// <returns>The rows written per table.</returns>
    IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload);

    /// <summary>Python <c>validate()</c>: the writer's post-write section-9 checks, as <c>(query, row_count)</c> per violation.</summary>
    /// <returns>The violations, empty when the run is sound.</returns>
    IReadOnlyList<(string Query, long RowCount)> Validate();
}

/// <summary>Saved base years a human chose (WI-21): Python <c>get_override_repository().base_years(client_id, program_code)</c>.</summary>
public interface IBaseYearOverrides
{
    /// <summary>The latest chosen base year per location.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The program.</param>
    /// <returns>Location id to base year.</returns>
    IReadOnlyDictionary<string, long> BaseYears(long clientId, string programCode);
}

/// <summary>Where the assessment records each claim (Python <c>get_claim_repository()</c>: <c>current</c> and <c>record</c>).</summary>
public interface IClaimSink
{
    /// <summary>The live claim of a cell, <c>null</c> when none.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The program.</param>
    /// <param name="taxYear">The year.</param>
    /// <returns>The claim or <c>null</c>.</returns>
    Claims.ProgramClaim? Current(long clientId, string programCode, long taxYear);

    /// <summary>Appends a claim.</summary>
    /// <param name="claim">The claim.</param>
    void Record(Claims.ProgramClaim claim);
}

/// <summary>Convenience over <see cref="FiscalWindow"/> for a window the pipeline measures: its dates.</summary>
public static class FiscalWindowExtensions
{
    /// <summary>The window as the <c>(begin, end)</c> pair the engine takes.</summary>
    /// <param name="window">The window.</param>
    /// <returns>The pair.</returns>
    public static (DateOnly Begin, DateOnly End) Span(this FiscalWindow window)
    {
        ArgumentNullException.ThrowIfNull(window);
        return (window.Begin, window.End);
    }
}
