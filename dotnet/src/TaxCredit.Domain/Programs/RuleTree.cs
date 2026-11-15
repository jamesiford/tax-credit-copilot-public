using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The dynamic-typing conveniences the rule tools lean on (a JSON tree read with <c>d.get(k)</c>, <c>d[k]</c>, <c>str(x)</c>,
/// <c>float(x)</c>), with CPython's exception types and messages for the shapes a malformed pack produces.
/// </summary>
internal static class RuleTree
{
    /// <summary>Python <c>x.get</c>: the dict itself, or the <c>AttributeError</c> a non-dict raises.</summary>
    internal static PyDict AsMapping(object? value) => value as PyDict
        ?? (value is null or bool or long or BigInteger or double or string or List<object?>
            ? throw new PyAttributeError($"'{ProximityCoerce.TypeName(value)}' object has no attribute 'get'")
            : throw new PyUnsupportedException("not a JSON value: " + value.GetType().Name));

    /// <summary>Python <c>container[key]</c> with a string key.</summary>
    internal static object? Sub(object? container, string key)
    {
        if (container is PyDict d)
        {
            return d[key];
        }

        throw container switch
        {
            string => new PyTypeError("string indices must be integers, not 'str'"),
            List<object?> => new PyTypeError("list indices must be integers or slices, not str"),
            null or bool or long or BigInteger or double => new PyTypeError($"'{ProximityCoerce.TypeName(container)}' object is not subscriptable"),
            _ => new PyUnsupportedException("not a JSON value: " + container.GetType().Name),
        };
    }

    /// <summary>Python <c>d.get(key)</c> (a PRESENT <c>None</c> is returned as <c>null</c>, like an absent key).</summary>
    internal static object? Get(PyDict d, string key) => d.TryGetValue(key, out var v) ? v : null;

    /// <summary>Python <c>d.get(key, default)</c>: a present value wins even when it is <c>None</c>.</summary>
    internal static object? Get(PyDict d, string key, object? fallback) => d.TryGetValue(key, out var v) ? v : fallback;

    /// <summary>A shallow copy (<c>dict(d)</c>).</summary>
    internal static PyDict Copy(PyDict d)
    {
        var copy = new PyDict();
        foreach (var kv in d)
        {
            copy.Add(kv.Key, kv.Value);
        }

        return copy;
    }

    /// <summary>Python <c>dict(x or {})</c> for a value that must be a mapping when truthy.</summary>
    internal static PyDict CopyOrEmpty(object? value) => ProximityCoerce.Truthy(value)
        ? value is PyDict d ? Copy(d) : throw new PyUnsupportedException("dict() of a non-mapping value is not modelled")
        : new PyDict();

    /// <summary>The tree value of an int: a <see cref="long"/> when it fits, a <see cref="BigInteger"/> otherwise (one CLR type per magnitude).</summary>
#pragma warning disable CA1859 // the object return is the point
    internal static object Int(BigInteger value) => value >= long.MinValue && value <= long.MaxValue ? (object)(long)value : value;
#pragma warning restore CA1859

    /// <summary>The magnitude of an int tree value.</summary>
    internal static BigInteger Big(object value) => value switch
    {
        long l => l,
        BigInteger b => b,
        bool x => x ? BigInteger.One : BigInteger.Zero,
        _ => throw new PyUnsupportedException("not an int: " + value.GetType().Name),
    };

    /// <summary>Python <c>round(x)</c> of a float, as an int tree value.</summary>
    internal static object RoundInt(double x) => Int(PyRound.RoundToInteger(x));

    /// <summary>Python <c>str(x)</c> of a tree value; a list or a dict prints as its <c>repr</c> (<c>['x']</c>, <c>{'a': 1}</c>).</summary>
    internal static string Str(object? value) => value switch
    {
        List<object?> or PyDict => Repr(value),
        _ => ProximityCoerce.Str(value),
    };

    private static string Repr(object? value) => value switch
    {
        null => "None",
        string s => PyStr.Repr(s),
        List<object?> list => "[" + string.Join(", ", list.Select(Repr)) + "]",
        PyDict d => "{" + string.Join(", ", d.Select(kv => PyStr.Repr(kv.Key) + ": " + Repr(kv.Value))) + "}",
        _ => ProximityCoerce.Str(value),
    };

    /// <summary>Python <c>float(x)</c>.</summary>
    internal static double Float(object? value) => ProximityCoerce.ToFloat(value);

    /// <summary>Python truthiness.</summary>
    internal static bool Truthy(object? value) => ProximityCoerce.Truthy(value);
}
