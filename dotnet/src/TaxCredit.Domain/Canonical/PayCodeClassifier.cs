using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Canonical;

/// <summary>Python <c>_pay_code_classifier</c> and <c>_is_includable</c> (DATA-05): which pay codes count towards the wage base.</summary>
/// <param name="Included">The included codes, or <c>null</c> to include everything not excluded.</param>
/// <param name="Excluded">The excluded codes; excluded wins.</param>
public sealed record PayCodeClassifier(HashSet<string>? Included, HashSet<string> Excluded)
{
    private static readonly string[] DefaultExcluded = ["Mileage", "Expense_Reimbursement", "Relocation"];

    /// <summary>Python <c>_is_includable(pay_code, included, excluded)</c>.</summary>
    /// <param name="payCode">The pay code.</param>
    /// <returns>Whether the line counts towards the wage base.</returns>
    public bool IsIncludable(string payCode)
    {
        if (Excluded.Contains(payCode))
        {
            return false;
        }

        return Included is null || Included.Contains(payCode);
    }

    /// <summary>
    /// Python <c>_pay_code_classifier(program)</c>: the ingested config's lists, or a conservative default (strip common non-taxable codes).
    /// </summary>
    /// <param name="program">The program code.</param>
    /// <param name="source">The ingested-config port (<c>null</c> is the 'none' source).</param>
    /// <returns>The classifier.</returns>
#pragma warning disable CA1031 // Python wraps the whole read in `except Exception` and falls back; any failure of the port or of the config's shape does the same
    public static PayCodeClassifier For(string program, IIngestedConfigSource? source)
    {
        try
        {
            var cfg = source?.Load(program);
            if (ProximityCoerce.Truthy(cfg))
            {
                var parameters = Mapping(Mapping(cfg).TryGetValue("parameters", out var p) ? OrEmpty(p) : null);
                var wb = Mapping(parameters.TryGetValue("wage_basis", out var w) ? OrEmpty(w) : null);
                wb.TryGetValue("included_pay_codes", out var inc);
                wb.TryGetValue("excluded_pay_codes", out var exc);
                var included = ProximityCoerce.Truthy(inc) ? ToSet(inc) : null;
                return new PayCodeClassifier(included, ToSet(ProximityCoerce.Truthy(exc) ? exc : new List<object?>()));
            }
        }
        catch (Exception)
        {
            // fall through to the default
        }

        return new PayCodeClassifier(null, [.. DefaultExcluded]);
    }
#pragma warning restore CA1031

    // Python `x or {}`: a falsy value reads as an empty dict.
    private static object OrEmpty(object? v) => ProximityCoerce.Truthy(v) ? v! : new PyDict();

    // Python `x.get(...)` on a non-dict raises AttributeError; the caller's broad except turns that into the default.
    private static PyDict Mapping(object? v) => v as PyDict ?? (v is null ? new PyDict() : throw new PyAttributeError("object has no attribute 'get'"));

    // Python `set(x)`: a string yields its code points, a list its items, a dict its keys; an unhashable item or a non-iterable is a TypeError.
    // Only strings can equal a pay code, so other hashable items are dropped.
    private static HashSet<string> ToSet(object? v)
    {
        var set = new HashSet<string>(StringComparer.Ordinal);
        switch (v)
        {
            case string s:
                for (var i = 0; i < s.Length; i += char.IsSurrogatePair(s, i) ? 2 : 1)
                {
                    set.Add(char.IsSurrogatePair(s, i) ? s.Substring(i, 2) : s[i].ToString());
                }

                return set;
            case PyDict d:
                set.UnionWith(d.Keys);
                return set;
            case List<object?> list:
                foreach (var item in list)
                {
                    if (item is string t)
                    {
                        set.Add(t);
                    }
                    else if (item is PyDict or List<object?>)
                    {
                        throw new PyTypeError("unhashable type: '" + ProximityCoerce.TypeName(item) + "'");
                    }
                }

                return set;
            case bool or long or BigInteger or double:
                throw new PyTypeError("'" + ProximityCoerce.TypeName(v) + "' object is not iterable");
            default:
                throw new PyTypeError("object is not iterable");
        }
    }
}
