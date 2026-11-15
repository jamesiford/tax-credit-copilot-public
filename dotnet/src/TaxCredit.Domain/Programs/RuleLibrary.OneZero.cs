using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

public sealed partial class RuleLibrary
{
    /// <summary>
    /// Python <c>credit_math.load_pack_one_zero</c>: builds a <see cref="OneZeroPack"/> from a state code or a credit code. [ADR-005]
    /// </summary>
    /// <remarks>
    /// An ingested cited config (the optional hook) may FILL values a pack lacks and may never OVERRIDE a year-resolved pack, because the ingested
    /// config is not year-scoped: letting it win would apply 2026 rules to 2021 payroll. The hook's failure never breaks the calculation
    /// (Python <c>except Exception</c>). When the hook answers, its <c>wage_basis</c>, <c>measuring_date</c> and pay codes DO replace the pack's, year-resolved or not.
    /// </remarks>
    /// <param name="stateOrCode">A two-letter state or a credit code (case-insensitive).</param>
    /// <param name="taxYear">The tax year, if any.</param>
    /// <returns>The pack, or <c>null</c> when no pack matches or it has no <c>one_zero</c> block.</returns>
    public OneZeroPack? LoadPackOneZero(string stateOrCode, long? taxYear = null)
    {
        ArgumentNullException.ThrowIfNull(stateOrCode);
        var s = PyStr.Upper(stateOrCode);
        var packFile = PackFileFor(s);
        if (packFile is null)
        {
            return null;
        }

        var (pack, yearResolved) = LoadYearPack(packFile, taxYear);
        var oz = RuleTree.Get(pack, "one_zero");
        if (!RuleTree.Truthy(oz))
        {
            return null;
        }

        var block = RuleTree.AsMapping(oz);
        var resolved = RuleTree.Copy(block);
        if (!yearResolved)
        {
            OverlayYear(block, resolved, taxYear);
        }

        var policyRaw = RuleTree.Get(block, "pay_code_policy");
        var policy = RuleTree.Truthy(policyRaw) ? RuleTree.AsMapping(policyRaw) : new PyDict();
        var included = RuleTree.Get(policy, "included_pay_codes");
        var excluded = RuleTree.Get(policy, "excluded_pay_codes");
        var ingested = Ingested(s, taxYear);
        if (ingested is { Count: > 0 })
        {
            var overridesFloors = !yearResolved; // [ADR-005] the cited config may FILL a floor a flat pack lacks, never OVERRIDE a year-resolved one (credit_math.load_pack_one_zero).
            if (overridesFloors)
            {
                resolved.Set("min_weekly_hours", ingested["min_weekly_hours"]);
                resolved.Set("min_weekly_wages", ingested["min_weekly_wages"]);
            }

            resolved.Set("wage_basis", RuleTree.Get(ingested, "wage_basis", RuleTree.Get(resolved, "wage_basis")));
            resolved.Set("measuring_date", RuleTree.Get(ingested, "measuring_date", RuleTree.Get(resolved, "measuring_date", "last_day")));
            if (RuleTree.Truthy(RuleTree.Get(ingested, "included_pay_codes")))
            {
                included = ingested["included_pay_codes"];
            }

            if (RuleTree.Truthy(RuleTree.Get(ingested, "excluded_pay_codes")))
            {
                excluded = ingested["excluded_pay_codes"];
            }
        }

        return OneZeroPackBuilder.Build(pack, resolved, included, excluded, taxYear);
    }

    // [H1] Legacy path: overlay year-specific thresholds onto the flat defaults. A materialised pack has them baked in.
    private static void OverlayYear(PyDict block, PyDict resolved, long? taxYear)
    {
        var tby = RuleTree.Get(block, "thresholds_by_year");
        if (!RuleTree.Truthy(tby) || taxYear is null)
        {
            return;
        }

        var yearBlock = RuleTree.Get(RuleTree.AsMapping(tby), taxYear.Value.ToString(CultureInfo.InvariantCulture));
        if (!RuleTree.Truthy(yearBlock))
        {
            return;
        }

        foreach (var kv in yearBlock as PyDict ?? throw new PyUnsupportedException("a year block that is not an object is not modelled"))
        {
            resolved.Set(kv.Key, kv.Value);
        }
    }

    private PyDict? Ingested(string key, long? taxYear)
    {
        if (_ingestion is null)
        {
            return null;
        }

        try
        {
            return _ingestion.IngestedOneZero(key, taxYear);
        }
        catch (Exception e) when (e is not (OutOfMemoryException or StackOverflowException))
        {
            // `except Exception` in credit_math.load_pack_one_zero: ingestion must never break the calculation.
            return null;
        }
    }
}
