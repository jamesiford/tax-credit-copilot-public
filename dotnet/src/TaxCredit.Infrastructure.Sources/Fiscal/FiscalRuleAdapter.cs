using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Fiscal;

/// <summary>Bounded fiscal I/O surface: two small tables, no payroll projection.</summary>
public interface IFiscalRuleReader
{
    /// <summary>Configuration readiness, not an outage catch.</summary>
    bool IsConfigured { get; }
    /// <summary>Stored rules in deterministic key order; null means unreadable, empty means read and absent.</summary>
    IReadOnlyList<FiscalRule>? Read(long accountId);
}

/// <summary>Source SQL rules via tenant-filtered Entity and bounded referenced rule IDs.</summary>
public sealed class SqlFiscalRuleReader(SourceScanner scanner) : IFiscalRuleReader
{
    /// <inheritdoc />
    public bool IsConfigured => scanner.IsConfigured;
    /// <inheritdoc />
    public IReadOnlyList<FiscalRule>? Read(long accountId)
    {
        var entities = scanner.Scan("Entity", accountId);
        IReadOnlyList<IReadOnlyDictionary<string, object?>> rules;
        try
        {
            rules = scanner.Scan("EntityFiscalYearRules", key: "fiscal_year_rules_id",
                ids: SourceDatasetReader.Keys(entities, "fiscal_year_rules_id"));
        }
        catch (SourceTableMissing) { return []; }
        return rules.OrderBy(r => SourceValues.Id(r, "fiscal_year_rules_id"))
            .Select(r => new FiscalRule(SourceValues.Text(r, "name"), SourceValues.Text(r, "rule_expression"),
                SourceValues.Date(r, "fiscal_year_begin"), SourceValues.Date(r, "fiscal_year_end"))).ToArray();
    }
}

/// <summary>Read diagnostics use only logical states, never customer values.</summary>
public sealed record FiscalReadDiagnostic(string SourceState, string Provider, bool FallbackUsed);

/// <summary>Fiscal I/O precedence around the certified pure resolver. Only typed outages can activate fixture fallback.</summary>
public sealed class FiscalRuleAdapter : IFiscalRuleSource
{
    private readonly IFiscalRuleReader _source;
    private readonly IFiscalRuleReader? _fallback;
    private readonly LookupResolver _lookups;
    private readonly bool _allowFallback;
    private readonly FiscalSource _resolver;

    /// <summary>Logical lakehouse SQL holds client rules; CSV explicitly does not.</summary>
    public FiscalRuleAdapter(RuleLibrary library, IFiscalRuleReader source, LookupResolver lookups,
        bool holdsClientRules = true, bool allowFixtureFallback = false, IFiscalRuleReader? fixtureFallback = null)
    {
        _source = source;
        _lookups = lookups;
        HoldsClientRules = holdsClientRules;
        _allowFallback = allowFixtureFallback;
        _fallback = fixtureFallback;
        _resolver = new FiscalSource(library, this);
    }

    /// <inheritdoc />
    public bool HoldsClientRules { get; }

    /// <summary>Source first; classified unreadability then opt-in fallback, then client/global authored overrides.</summary>
    public (IReadOnlyList<FiscalRule>? Rules, FiscalReadDiagnostic Diagnostic) ReadWithDiagnostic(long accountId)
    {
        IReadOnlyList<FiscalRule>? rules = null;
        var state = _source.IsConfigured ? "unreadable" : "unconfigured";
        var fallbackUsed = false;
        if (_source.IsConfigured)
        {
            try { rules = _source.Read(accountId); }
            catch (SourceUnavailable) { rules = null; }
        }
        if (rules is null && _allowFallback)
        {
            if (_fallback is null || !_fallback.IsConfigured) { throw new SourceUnavailable("source_fixture_fallback"); }
            rules = _fallback.Read(accountId);
            fallbackUsed = true;
        }
        if (rules is not null) { state = rules.Count == 0 ? "empty" : "present"; }
        if (rules is { Count: > 0 })
        {
            ValidateStrictRules(rules, accountId);
            return (rules, new FiscalReadDiagnostic(state, fallbackUsed ? "materialized_fixture" : "source", fallbackUsed));
        }
        var overrides = _lookups.FiscalOverrides(accountId);
        if (overrides.Count > 0)
        {
            ValidateStrictRules(overrides, accountId);
            return (overrides, new FiscalReadDiagnostic(state, "override", fallbackUsed));
        }
        if (_lookups.Options.FiscalPolicy == "strict") { throw new FiscalRulesMissing(); }
        return (rules, new FiscalReadDiagnostic(state, "assumed_calendar", fallbackUsed));
    }

    /// <inheritdoc />
    public IReadOnlyList<FiscalRule>? RulesWithOverrides(long accountId) => ReadWithDiagnostic(accountId).Rules;

    /// <summary>Same pure arithmetic as the certified pipeline, with a strict representability gate.</summary>
    public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention)
    {
        if (HoldsClientRules && accountId is { } account && _lookups.Options.FiscalPolicy == "strict")
        {
            var rules = RulesWithOverrides(account);
            if (rules is null || !rules.Any(r => FiscalSource.WindowFromRule(r, account, taxYear, convention) is not null))
            {
                throw new FiscalRulesMissing();
            }
        }
        return _resolver.ClientFiscalWindow(accountId, taxYear, convention);
    }

    /// <summary>Missing authored convention returns null; typed lookup/dependency failures propagate.</summary>
    public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear)
    {
        var window = _resolver.FiscalWindowForStateYear(accountId, state, taxYear);
        if (window is { Assumed: true } && HoldsClientRules && accountId is not null && _lookups.Options.FiscalPolicy == "strict")
        {
            throw new FiscalRulesMissing();
        }
        return window;
    }

    /// <summary>Date-only callers still use the provenance-bearing resolver.</summary>
    public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
        FiscalWindowForStateYear(accountId, state, taxYear) is { } window ? (window.Begin, window.End) : null;

    private void ValidateStrictRules(IReadOnlyList<FiscalRule> rules, long accountId)
    {
        if (_lookups.Options.FiscalPolicy != "strict") { return; }
        var valid = rules.Any(r =>
        {
            var row = new Dictionary<string, object?> { ["begin"] = r.FiscalYearBegin, ["end"] = r.FiscalYearEnd };
            var begin = SourceValues.Date(row, "begin");
            return begin is { } date && FiscalSource.WindowFromRule(r, accountId, date.Year, "begins") is not null;
        });
        if (!valid) { throw new FiscalRulesMissing(); }
    }
}
