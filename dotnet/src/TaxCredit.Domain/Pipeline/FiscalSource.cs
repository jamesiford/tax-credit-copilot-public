using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Pipeline;

/// <summary>
/// Where a client's fiscal year actually comes from (Python <c>infrastructure/payroll/fiscal_source.py</c>): the stored rule shifted onto the requested tax
/// year, or a flagged calendar-year assumption. The SQL and lakehouse reads are behind <see cref="IFiscalRuleSource"/>; the arithmetic here is pure.
/// </summary>
/// <param name="library">The rule library (a program's tax-year convention).</param>
/// <param name="rules">The stored rules and the source mode.</param>
public sealed class FiscalSource(RuleLibrary library, IFiscalRuleSource rules)
{
    /// <summary>Python <c>client_fiscal_window</c>: the client's own window for a tax year, or a flagged assumption.</summary>
    /// <remarks>
    /// The stored rule is ONE window (the client's base year); later years shift by whole years, which is how a repeating calendar works. A 53-week calendar
    /// drifts a few days a year and this does not model that, so a shifted window is returned only when it can represent the year.
    /// </remarks>
    /// <param name="accountId">The client; <c>null</c> has no rules.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="convention"><c>begins</c> or <c>ends</c>.</param>
    /// <returns>The window.</returns>
    public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention)
    {
        if (accountId is not { } account)
        {
            return FiscalWindow.AssumedCalendar(taxYear, convention);
        }

        // Why: only the lakehouse holds per-client rules; reading them while payroll comes from elsewhere pairs one client's calendar with another source's paychecks.
        if (!rules.HoldsClientRules)
        {
            return FiscalWindow.AssumedCalendar(taxYear, convention);
        }

        var stored = rules.RulesWithOverrides(account);
        if (stored is null)
        {
            return FiscalWindow.AssumedCalendar(taxYear, convention);
        }

        foreach (var rule in stored)
        {
            if (WindowFromRule(rule, account, taxYear, convention) is { } window)
            {
                return window;
            }
        }

        return FiscalWindow.AssumedCalendar(taxYear, convention);
    }

    /// <summary>Python <c>fiscal_window_for_state_year</c>: the window WITH its provenance, or <c>null</c> for a state with no programme to take a convention from.</summary>
    /// <param name="accountId">The client.</param>
    /// <param name="state">A state, or a program code (which names its own convention).</param>
    /// <param name="taxYear">The tax year.</param>
    /// <returns>The window or <c>null</c>.</returns>
    public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear)
    {
        var key = PyStr.Upper(state ?? string.Empty);
        var forState = library.ProgramsForState(key);
        var entry = library.ProgramForCode(key) ?? (forState.Count > 0 ? forState[0] : null);
        if (entry is null)
        {
            return null;
        }

        string label;
        try
        {
            label = (string)library.ResolveTaxYearConvention(entry.Code, taxYear)["label"]!;
        }
        catch (Exception e) when (e is PyFileNotFoundError or PyValueError or PyKeyError)
        {
            // A year with no authored statute has no window.
            return null;
        }

        return ClientFiscalWindow(accountId, taxYear, label);
    }

    /// <summary>Python <c>window_for_state_year</c>: <see cref="FiscalWindowForStateYear"/> as plain dates.</summary>
    /// <param name="accountId">The client.</param>
    /// <param name="state">A state or program code.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <returns>The dates or <c>null</c>.</returns>
    public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
        FiscalWindowForStateYear(accountId, state, taxYear) is { } window ? (window.Begin, window.End) : null;

    /// <summary>Python <c>_window_from_rule</c>: the rule's window shifted onto <paramref name="taxYear"/>, or <c>null</c> when it cannot represent that year.</summary>
    /// <param name="rule">The stored rule.</param>
    /// <param name="accountId">The client, for the note.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="convention"><c>begins</c> or <c>ends</c>.</param>
    /// <returns>The window or <c>null</c>.</returns>
    public static FiscalWindow? WindowFromRule(FiscalRule rule, long accountId, long taxYear, string convention)
    {
        ArgumentNullException.ThrowIfNull(rule);
        if (AsDate(rule.FiscalYearBegin) is not { } begin || AsDate(rule.FiscalYearEnd) is not { } end || end < begin)
        {
            return null;
        }

        var shift = taxYear - (convention == "begins" ? begin.Year : end.Year);
        DateOnly shiftedBegin, shiftedEnd;
        try
        {
            shiftedBegin = PyDate.Replace(begin, year: checked((int)(begin.Year + shift)));
            shiftedEnd = PyDate.Replace(end, year: checked((int)(end.Year + shift)));
        }
        catch (Exception e) when (e is PyValueError or OverflowException)
        {
            // 29 Feb into a common year, or a year outside 1..9999.
            return null;
        }

        return FiscalWindow.FromClientRules(shiftedBegin, shiftedEnd, convention, RuleNote(rule, accountId, begin, end, shift));
    }

    // Python `_as_date`: None, a date, or `date.fromisoformat(str(value)[:10])` with an unparseable text reading as None.
    private static DateOnly? AsDate(object? value) => value switch
    {
        null => null,
        DateOnly d => d,
        string s => PyDate.TryFromIsoFormat(PyStr.Prefix(s, 10), out var parsed) ? parsed : null,
        _ => throw new PyUnsupportedException("a fiscal-year bound of type " + value.GetType().Name + " is not modelled"),
    };

    private static string RuleNote(FiscalRule rule, long accountId, DateOnly begin, DateOnly end, long shift)
    {
        var origin = (rule.Name ?? "None").StartsWith("override:", StringComparison.Ordinal) ? "an app-owned override" : "EntityFiscalYearRules";
        var text = string.Create(CultureInfo.InvariantCulture, $"From {origin} for account {accountId}")
            + (string.IsNullOrEmpty(rule.RuleExpression) ? string.Empty : $" ({rule.RuleExpression})");
        if (shift == 0)
        {
            return text + ".";
        }

        var signed = shift >= 0 ? "+" + shift.ToString(CultureInfo.InvariantCulture) : shift.ToString(CultureInfo.InvariantCulture);
        return $"{text}, shifted {signed} year(s) from the stored base window {Iso(begin)}..{Iso(end)}.";
    }

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}
