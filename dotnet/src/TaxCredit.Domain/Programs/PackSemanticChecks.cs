using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The semantic rules of <c>tools/pack_validation.py</c>: what a schema cannot say (the file is named for what it holds, the engine can price the
/// benefit, a year's floors agree with the pack's own, a <c>_verified</c> claim has its sources). Each method is one Python function and adds to the
/// report in the same order.
/// </summary>
/// <remarks>
/// A malformed pack reaches these checks (the schema findings do not stop them), so Python's dynamic behaviour is mirrored: <c>x or {}</c> keeps
/// a truthy non-mapping, and <c>.get</c> on it raises <c>AttributeError</c>; <c>"k" in value</c> is a substring test on text, a membership test on a list
/// and a <c>TypeError</c> on a number. Those exceptions propagate out of the validator in Python, so they do here.
/// </remarks>
internal static class PackSemanticChecks
{
    private const string PrototypeVerify = "_prototype_verify";

    /// <summary>Python <c>_flags</c>: the path of every <c>_prototype_verify: true</c> in the pack, in document order (a flag on the root is <c>/</c>).</summary>
    internal static List<string> Flags(object? node, string path = "")
    {
        var found = new List<string>();
        if (node is PyDict dict)
        {
            foreach (var kv in dict)
            {
                if (kv.Key == PrototypeVerify && kv.Value is true)
                {
                    found.Add(path.Length > 0 ? path : "/");
                }

                found.AddRange(Flags(kv.Value, $"{path}/{kv.Key}"));
            }
        }
        else if (node is List<object?> list)
        {
            for (var i = 0; i < list.Count; i++)
            {
                found.AddRange(Flags(list[i], $"{path}/{i}"));
            }
        }

        return found;
    }

    /// <summary>Python <c>_check_models</c>: the benefit must be a model the engine prices, and the methodology block must be one it reads.</summary>
    internal static void CheckModels(PyDict pack, string kind, bool yearsAuthored, PackReport report)
    {
        var benefit = OrEmpty(RuleTree.Get(pack, "benefit"));
        if (In("amount_per_qualifying_job_pct_of_wages", benefit))
        {
            // Describable today (a pack may record the statute), but the engine prices only a flat per-job amount.
            var severity = kind == PackKinds.Year || yearsAuthored ? "error" : "warning";
            report.Add(severity, "unsupported_credit_model",
                $"percentage-of-wages benefit is not a supported credit model ({string.Join(", ", ProgramVocabulary.SupportedCreditModels)}); "
                + "it needs engine work before this program can be priced", "benefit");
        }

        var oz = Mapping(RuleTree.Get(pack, "one_zero"));
        try
        {
            _ = OneZeroMethodologyJson.FromPackJson(RuleTree.Get(oz, "methodology"));
        }
        catch (PyValueError exc)
        {
            report.Add("error", "unsupported_methodology", exc.Message, "one_zero/methodology");
        }
    }

    /// <summary>Python <c>_check_thresholds</c>: a year's floors in <c>thresholds_by_year</c> must equal the pack's own.</summary>
    internal static void CheckThresholds(PyDict pack, PackReport report)
    {
        var oz = Mapping(RuleTree.Get(pack, "one_zero"));
        var byYear = OrEmpty(RuleTree.Get(oz, "thresholds_by_year"));
        var year = RuleTree.Get(pack, "tax_year");

        // `.get` is only called when there is a year, so a malformed table raises only then.
        var block = year is not null ? RuleTree.Get(RuleTree.AsMapping(byYear), RuleTree.Str(year)) : null;
        if (!RuleTree.Truthy(block))
        {
            return;
        }

        foreach (var key in new[] { "min_weekly_hours", "min_weekly_wages" })
        {
            // `block[key]` on a non-mapping raises TypeError (text and lists pass the `in` test above it by substring and membership).
            if (In(key, block) && !PyEquality.Equal(RuleTree.Sub(block, key), RuleTree.Get(oz, key)))
            {
                report.Add("error", "thresholds_by_year",
                    $"{key} {RuleTree.Str(RuleTree.Sub(block, key))} for {RuleTree.Str(year)} disagrees with the pack's own {RuleTree.Str(RuleTree.Get(oz, key))}",
                    $"one_zero/thresholds_by_year/{RuleTree.Str(year)}/{key}");
            }
        }
    }

    /// <summary>Python <c>_check_verified_claim</c>: a pack may claim <c>_verified: true</c> only with no outstanding flag and with its sources named.</summary>
    internal static void CheckVerifiedClaim(PyDict pack, PackReport report)
    {
        if (RuleTree.Get(pack, "_verified") is not true)
        {
            return;
        }

        foreach (var path in Flags(pack))
        {
            report.Add("error", "verified_with_flags", "claims _verified but still carries _prototype_verify", path);
        }

        // `not A or not B` short-circuits: the provenance is only read when the citation is present.
        if (!RuleTree.Truthy(RuleTree.Get(Mapping(RuleTree.Get(pack, "credit")), "statutory_citation"))
            || !RuleTree.Truthy(RuleTree.Get(Mapping(RuleTree.Get(pack, "_year_provenance")), "source")))
        {
            report.Add("error", "verified_without_citation", "a verified pack needs credit.statutory_citation and _year_provenance.source");
        }
    }

    /// <summary>Python <c>_check_names</c>: a year pack is named for its tax year; a base pack starts with its jurisdiction.</summary>
    internal static void CheckNames(string name, PyDict pack, string kind, PackReport report)
    {
        if (kind == PackKinds.Year)
        {
            if (name.Split('.')[0] != RuleTree.Str(RuleTree.Get(pack, "tax_year")))
            {
                report.Add("error", "filename", $"{name} must be named for its tax_year ({RuleTree.Str(RuleTree.Get(pack, "tax_year"))}.json)");
            }

            return;
        }

        var j = Mapping(RuleTree.Get(pack, "jurisdiction"));
        var level = RuleTree.Get(j, "level");
        var expected = level is "federal" ? "federal_" : PackText.Lower(RuleTree.Str(RuleTree.Get(j, "code", string.Empty))) + "_";
        if (!name.StartsWith(expected, StringComparison.Ordinal))
        {
            report.Add("error", "filename", $"{name} must start with {PyStr.Repr(expected)} for a {RuleTree.Str(level)} pack");
        }
    }

    /// <summary>Python <c>x or {}</c> followed by <c>.get</c>: the mapping, an empty one for a falsy value, and <c>AttributeError</c> for any other truthy value.</summary>
    internal static PyDict Mapping(object? value) => RuleTree.Truthy(value) ? RuleTree.AsMapping(value) : new PyDict();

    /// <summary>Python <c>x or {}</c> alone: the value, or an empty mapping when it is falsy.</summary>
    internal static object OrEmpty(object? value) => RuleTree.Truthy(value) ? value! : new PyDict();

    /// <summary>Python <c>key in container</c> for a string key: key lookup, substring test, list membership, or the <c>TypeError</c> a number raises.</summary>
    internal static bool In(string key, object? container) => container switch
    {
        PyDict d => d.ContainsKey(key),
        string s => s.Contains(key, StringComparison.Ordinal),
        List<object?> list => list.Any(x => PyEquality.Equal(x, key)),
        _ => throw new PyTypeError($"argument of type '{ProximityCoerce.TypeName(container)}' is not iterable"),
    };
}
