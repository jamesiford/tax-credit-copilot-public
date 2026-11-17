using System.Numerics;

namespace TaxCredit.Domain.Numerics;

/// <summary>Python <c>==</c> over the value kinds a parsed JSON tree holds (<c>None</c>, bool, int, float, str, list, dict).</summary>
/// <remarks>
/// Why a type of its own: <c>1 == 1.0 == True</c> in Python, <c>{"a": 1, "b": 2} == {"b": 2, "a": 1}</c> (dict equality ignores
/// order) and a <c>dataclass</c>'s generated <c>__eq__</c> compares its dict-valued fields this way. C# <c>object.Equals</c> would
/// say none of those. Not modelled: NaN compared with itself inside a container (CPython short-circuits on identity there).
/// </remarks>
public static class PyEquality
{
    /// <summary>Python <c>a == b</c>.</summary>
    /// <param name="a">The left value.</param>
    /// <param name="b">The right value.</param>
    /// <returns>Whether Python would report them equal.</returns>
    public static bool Equal(object? a, object? b)
    {
        if (a is null || b is null)
        {
            return a is null && b is null;
        }

        if (IsNumber(a) && IsNumber(b))
        {
            return NumbersEqual(a, b);
        }

        return (a, b) switch
        {
            (string x, string y) => string.Equals(x, y, StringComparison.Ordinal),
            (PyDict x, PyDict y) => DictsEqual(x, y),
            (List<object?> x, List<object?> y) => x.Count == y.Count && x.Zip(y).All(p => Equal(p.First, p.Second)),
            _ => false,
        };
    }

    private static bool IsNumber(object v) => v is bool or long or BigInteger or double;

    private static bool DictsEqual(PyDict x, PyDict y)
    {
        if (x.Count != y.Count)
        {
            return false;
        }

        foreach (var kv in x)
        {
            if (!y.TryGetValue(kv.Key, out var other) || !Equal(kv.Value, other))
            {
                return false;
            }
        }

        return true;
    }

    private static bool NumbersEqual(object a, object b)
    {
        if (a is double da)
        {
            return b is double db ? da == db : FloatEqualsInt(da, ToBig(b));
        }

        return b is double d2 ? FloatEqualsInt(d2, ToBig(a)) : ToBig(a) == ToBig(b);
    }

    // CPython compares an int with a float exactly (not by converting the int to a double first).
    private static bool FloatEqualsInt(double d, BigInteger i) =>
        double.IsFinite(d) && Math.Floor(d) == d && new BigInteger(d) == i;

    private static BigInteger ToBig(object v) => v switch
    {
        bool x => x ? BigInteger.One : BigInteger.Zero,
        long x => x,
        BigInteger x => x,
        _ => throw new InvalidOperationException("not an int"),
    };
}
