using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// The Python conversions <c>proximity.py</c> applies to loosely typed row values (<c>float(x or 0.0)</c>, <c>int(x)</c>,
/// <c>str(x)</c>, truthiness) and the exact int-to-float arithmetic it relies on.
/// </summary>
/// <remarks>
/// Why a layer: rows arrive as dictionaries whose values may be <c>None</c>, ints, bools, numeric strings or junk, and the
/// module's behaviour (which exception, which fallback) depends on Python's conversion rules, not on C# casts.
/// </remarks>
internal static class ProximityCoerce
{
    private const int Mantissa = 53;

    /// <summary>Python truthiness of a tree value.</summary>
    internal static bool Truthy(object? v) => v switch
    {
        null => false,
        bool b => b,
        long l => l != 0,
        BigInteger i => !i.IsZero,
        double d => d != 0,
        string s => s.Length > 0,
        PyDict dict => dict.Count > 0,
        System.Collections.ICollection c => c.Count > 0,
        _ => true,
    };

    /// <summary>Python truthiness of an int-or-float.</summary>
    internal static bool Truthy(PyNumber n) => n.IsInt ? n.IntValue != 0 : n.FloatValue != 0;

    /// <summary>Python <c>float(n)</c> of an int-or-float.</summary>
    internal static double ToFloat(PyNumber n) => n.IsInt ? n.IntValue : n.FloatValue;

    /// <summary>Python <c>float(row.get(key) or 0.0)</c>: a falsy value (missing, <c>None</c>, zero, empty) reads as 0.0.</summary>
    internal static double FloatOrZero(PyDict row, string key) =>
        row.TryGetValue(key, out var v) && Truthy(v) ? ToFloat(v) : 0.0;

    /// <summary>Python <c>float(v)</c> for a tree value.</summary>
    /// <exception cref="PyValueError">For text that is not a number.</exception>
    /// <exception cref="PyTypeError">For a value Python's <c>float()</c> rejects (None, list, dict).</exception>
    /// <exception cref="PyOverflowError">For an int too large for a double.</exception>
    internal static double ToFloat(object? v)
    {
        switch (v)
        {
            case double d:
                return d;
            case long l:
                return l;
            case bool b:
                return b ? 1.0 : 0.0;
            case BigInteger i:
                var f = ExactTrueDiv(i, BigInteger.One);
                return double.IsInfinity(f) ? throw new PyOverflowError("int too large to convert to float") : f;
            case string s:
                return PyFloat.TryParse(s, out var parsed) ? parsed : throw new PyValueError("could not convert string to float: " + Repr(s));
            default:
                throw new PyTypeError("float() argument must be a string or a real number, not '" + TypeName(v) + "'");
        }
    }

    /// <summary>Python <c>int(v)</c> for a tree value, as a <c>long</c> when it fits and a <see cref="BigInteger"/> otherwise.</summary>
    internal static object ToInt(object? v)
    {
        switch (v)
        {
            case long l:
                return l;
            case bool b:
                return b ? 1L : 0L;
            case BigInteger i:
                return Normalise(i);
            case double d:
                return Normalise(PyArith.Truncate(d));
            case string s:
                return PyInt.TryParse(s, out var parsed) ? Normalise(parsed) : throw new PyValueError("invalid literal for int() with base 10: " + Repr(s));
            default:
                throw new PyTypeError("int() argument must be a string, a bytes-like object or a real number, not '" + TypeName(v) + "'");
        }
    }

    /// <summary>Python <c>str(v)</c> for the value kinds an employee id can take.</summary>
    internal static string Str(object? v) => v switch
    {
        null => "None",
        string s => s,
        bool b => b ? "True" : "False",
        long l => l.ToString(System.Globalization.CultureInfo.InvariantCulture),
        BigInteger i => i.ToString(System.Globalization.CultureInfo.InvariantCulture),
        double d => PyFloat.Repr(d),
        _ => throw new PyUnsupportedException("str() of " + TypeName(v) + " is not modelled"),
    };

    /// <summary>Python <c>repr(str)</c> for the text shown in conversion error messages.</summary>
    internal static string Repr(string s) => PyStr.Repr(s);

    /// <summary>Python <c>int / int</c>: the correctly rounded quotient (CPython <c>long_true_divide</c>), denominator positive.</summary>
    /// <remarks>
    /// Why not <c>(double)n / d</c>: converting a big numerator first rounds twice. The quotient is formed with 60-62
    /// significant bits plus a sticky bit and rounded once, half to even.
    /// </remarks>
    internal static double ExactTrueDiv(BigInteger n, BigInteger d)
    {
        if (n.IsZero)
        {
            return 0.0;
        }

        var a = BigInteger.Abs(n);
        var shift = 61 - ((int)a.GetBitLength() - (int)d.GetBitLength());
        var q = shift >= 0
            ? BigInteger.DivRem(a << shift, d, out var r)
            : BigInteger.DivRem(a, d << -shift, out r);
        var bits = (int)q.GetBitLength();
        var m = (ulong)q;
        if (!r.IsZero)
        {
            m |= 1;
        }

        var extra = bits - Mantissa;
        var mant = m >> extra;
        var rest = m & ((1UL << extra) - 1);
        var half = 1UL << (extra - 1);
        if (rest > half || (rest == half && (mant & 1) == 1))
        {
            mant++;
        }

        var value = Math.ScaleB((double)mant, extra - shift);
        return n.Sign < 0 ? -value : value;
    }

    /// <summary>Python <c>math.ceil(x * step - 1e-9) / step</c> with an int <paramref name="step"/>.</summary>
    internal static double CeilOver(double scaled, long step) =>
        ExactTrueDiv(PyArith.Ceil(scaled - 1e-9), step);

    /// <summary>
    /// <c>_round_half_up</c> with the exceptions Python's <c>decimal</c> raises: a NaN passes through unchanged, an infinity
    /// raises <c>InvalidOperation</c> whose message is <c>[&lt;class 'decimal.InvalidOperation'&gt;]</c>.
    /// </summary>
    internal static double RoundHalfUp(double value, int places)
    {
        if (double.IsNaN(value))
        {
            return double.NaN;
        }

        try
        {
            return OneZeroEligibility.RoundHalfUp(value, places);
        }
        catch (PyInvalidOperation)
        {
            throw new PyInvalidOperation("[<class 'decimal.InvalidOperation'>]");
        }
    }

    /// <summary>The Python type name used in <c>TypeError</c> messages.</summary>
    internal static string TypeName(object? v) => v switch
    {
        null => "NoneType",
        string => "str",
        bool => "bool",
        long or BigInteger => "int",
        double => "float",
        PyDict => "dict",
        System.Collections.IEnumerable => "list",
        _ => v.GetType().Name,
    };

    /// <summary>A <c>KeyError</c> whose message is Python's <c>str(KeyError(key))</c>, the key's repr.</summary>
    internal static PyKeyError Missing(string key) => new(key);

    // `cond ? (long)i : i` would silently convert the long to BigInteger (conditional-type trap, see slice-domain-log DS2).
#pragma warning disable CA1859 // the object return is the point: a long when it fits, a BigInteger otherwise
    private static object Normalise(BigInteger i)
    {
        if (i >= long.MinValue && i <= long.MaxValue)
        {
            return (long)i;
        }

        return i;
    }
#pragma warning restore CA1859
}
