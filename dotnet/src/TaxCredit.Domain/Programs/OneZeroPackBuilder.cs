using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// Builds a <see cref="OneZeroPack"/> (the eligibility floors) from a rule pack document (Python <c>tools/one_zero_pack.py</c>): the one place a pack's
/// <c>one_zero</c> block becomes the engine's parameters. [ADR-013, F05]
/// </summary>
public static class OneZeroPackBuilder
{
    /// <summary>
    /// Python <c>build_one_zero_pack</c>. The floors are ALWAYS floats here, whatever the pack held (<c>float(resolved[...])</c>), while the int
    /// or float a pack declares stays visible in the year pack and its trail.
    /// </summary>
    /// <param name="pack">The pack document.</param>
    /// <param name="resolved">The pack's <c>one_zero</c> block after any year overlay.</param>
    /// <param name="includedPayCodes">Pay codes counted, or <c>null</c>/empty for all.</param>
    /// <param name="excludedPayCodes">Pay codes suppressed, or <c>null</c>/empty for none.</param>
    /// <param name="taxYear">The tax year the floors were resolved for.</param>
    /// <returns>The pack.</returns>
    /// <exception cref="PyKeyError">When <c>one_zero</c> or a required floor is missing.</exception>
    public static OneZeroPack Build(PyDict pack, PyDict resolved, object? includedPayCodes, object? excludedPayCodes, long? taxYear)
    {
        ArgumentNullException.ThrowIfNull(pack);
        ArgumentNullException.ThrowIfNull(resolved);
        var ozRaw = pack["one_zero"];
        var ptBand = RuleTree.Get(resolved, "pt_band_hours");
        var ptWeight = RuleTree.Get(resolved, "pt_weight");
        // Keyword arguments are evaluated left to right in Python, so the first failing conversion decides the exception.
        var hours = Float(resolved["min_weekly_hours"]);
        var wages = Float(RuleTree.Get(resolved, "min_weekly_wages", 0.0));
        var wageBasis = RuleTree.Str(RuleTree.Get(resolved, "wage_basis", RuleTree.Get(RuleTree.AsMapping(ozRaw), "wage_basis", "regular")));
        var oz = RuleTree.AsMapping(ozRaw);
        var granularity = RuleTree.Str(RuleTree.Get(oz, "geographic_granularity", "unit"));
        var ptAggregation = RuleTree.Truthy(RuleTree.Get(oz, "pt_aggregation", false));
        var unitField = RuleTree.Str(RuleTree.Get(oz, "headcount_unit_field", "Worksite_ID"));
        var citation = RuleTree.Str(RuleTree.Get(RuleTree.AsMapping(RuleTree.Get(pack, "credit", new PyDict())), "statutory_citation", string.Empty));
        var band = RuleTree.Truthy(ptBand) ? Band(ptBand) : ((PyNumber, PyNumber)?)null;
        PyNumber? weight = RuleTree.Truthy(ptWeight) ? PyNumber.OfFloat(Float(ptWeight)) : null;
        var measuring = RuleTree.Str(RuleTree.Get(resolved, "measuring_date", RuleTree.Get(oz, "measuring_date", "last_day")));
        var combination = RuleTree.Str(RuleTree.Get(oz, "entity_combination", "permitted"));
        return new OneZeroPack
        {
            MinWeeklyHours = PyNumber.OfFloat(hours),
            MinWeeklyWages = PyNumber.OfFloat(wages),
            WageBasis = wageBasis,
            GeographicGranularity = granularity,
            PtAggregation = ptAggregation,
            HeadcountUnitField = unitField,
            Citation = citation,
            PtBandHours = band,
            PtWeight = weight,
            MeasuringDate = measuring,
            EntityCombination = combination,
            IncludedPayCodes = Codes(includedPayCodes),
            ExcludedPayCodes = Codes(excludedPayCodes),
            TaxYear = taxYear,
            Methodology = OneZeroMethodologyJson.FromPackJson(RuleTree.Get(oz, "methodology")),
        };
    }

    /// <summary>Python <c>pack_from_document</c>: the parameters a year-resolved document carries, as the engine reads a materialised year pack (no overlays).</summary>
    /// <param name="pack">The pack document.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <returns>The pack.</returns>
    public static OneZeroPack FromDocument(PyDict pack, long? taxYear)
    {
        ArgumentNullException.ThrowIfNull(pack);
        var oz = RuleTree.AsMapping(pack["one_zero"]);
        var policyRaw = RuleTree.Get(oz, "pay_code_policy");
        var policy = RuleTree.Truthy(policyRaw) ? RuleTree.AsMapping(policyRaw) : new PyDict();
        return Build(pack, RuleTree.Copy(oz), RuleTree.Get(policy, "included_pay_codes"), RuleTree.Get(policy, "excluded_pay_codes"), taxYear);
    }

    private static double Float(object? value) => RuleTree.Float(value);

    // `(float(pt_band[0]), float(pt_band[1]))`: a list shorter than two raises IndexError, exactly as Python.
    private static (PyNumber, PyNumber)? Band(object? band)
    {
        if (band is not List<object?> list)
        {
            throw new PyUnsupportedException("pt_band_hours that is not a list is not modelled");
        }

        var low = list.Count > 0 ? Float(list[0]) : throw new PyIndexError("list index out of range");
        var high = list.Count > 1 ? Float(list[1]) : throw new PyIndexError("list index out of range");
        return (PyNumber.OfFloat(low), PyNumber.OfFloat(high));
    }

    // `tuple(codes) if codes else None`
    private static List<string>? Codes(object? codes)
    {
        if (!RuleTree.Truthy(codes))
        {
            return null;
        }

        return codes is List<object?> list
            ? list.Select(c => c as string ?? throw new PyUnsupportedException("a pay code that is not text is not modelled")).ToList()
            : throw new PyUnsupportedException("pay codes that are not a list are not modelled");
    }
}
