using System.Numerics;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python arithmetic that differs from C#: floor division and modulo, true division errors, <c>int()</c>,
/// <c>math.floor/ceil</c>, and <c>min</c>/<c>max</c> tie and NaN behaviour.
/// </summary>
/// <remarks>
/// Why not the operators: C# <c>/</c> and <c>%</c> on integers truncate toward zero while Python floors;
/// C# <c>double / 0</c> is infinity where Python raises; <c>Math.Floor(a / b)</c> is not Python's float
/// <c>//</c> (CPython derives the quotient from <c>fmod</c> to keep <c>a == (a//b)*b + a%b</c> exact);
/// <c>Math.Min(-0.0, 0.0)</c> is <c>-0.0</c> but Python's <c>min(0.0, -0.0)</c> is <c>0.0</c> (first wins on ties).
/// Source: CPython <c>Objects/floatobject.c</c> (<c>float_divmod</c>, <c>float_rem</c>, <c>float_floor_div</c>).
/// </remarks>
public static class PyArith
{
    /// <summary>Python <c>a // b</c> for ints.</summary>
    public static BigInteger FloorDiv(BigInteger a, BigInteger b)
    {
        if (b.IsZero)
        {
            throw new PyZeroDivisionError("integer division or modulo by zero");
        }

        var q = BigInteger.DivRem(a, b, out var r);
        return !r.IsZero && (r.Sign < 0) != (b.Sign < 0) ? q - 1 : q;
    }

    /// <summary>Python <c>a % b</c> for ints (result has the sign of <paramref name="b"/>).</summary>
    public static BigInteger Mod(BigInteger a, BigInteger b)
    {
        if (b.IsZero)
        {
            throw new PyZeroDivisionError("integer division or modulo by zero");
        }

        var r = BigInteger.Remainder(a, b);
        return !r.IsZero && (r.Sign < 0) != (b.Sign < 0) ? r + b : r;
    }

    /// <summary>Python <c>a // b</c> for floats.</summary>
    public static double FloorDiv(double a, double b) => DivMod(a, b).Quotient;

    /// <summary>Python <c>a % b</c> for floats (result has the sign of <paramref name="b"/>).</summary>
    public static double Mod(double a, double b)
    {
        if (b == 0)
        {
            throw new PyZeroDivisionError("division by zero");
        }

        var mod = a % b; // C# % on doubles is C fmod, as CPython uses
        if (mod != 0)
        {
            if ((b < 0) != (mod < 0))
            {
                mod += b;
            }
        }
        else
        {
            mod = Math.CopySign(0.0, b);
        }

        return mod;
    }

    /// <summary>Python <c>divmod(a, b)</c> for floats.</summary>
    public static (double Quotient, double Remainder) DivMod(double a, double b)
    {
        if (b == 0)
        {
            throw new PyZeroDivisionError("division by zero");
        }

        var mod = a % b;
        var div = (a - mod) / b;
        if (mod != 0)
        {
            if ((b < 0) != (mod < 0))
            {
                mod += b;
                div -= 1.0;
            }
        }
        else
        {
            mod = Math.CopySign(0.0, b);
        }

        double floorDiv;
        if (div != 0)
        {
            floorDiv = Math.Floor(div);
            if (div - floorDiv > 0.5)
            {
                floorDiv += 1.0;
            }
        }
        else
        {
            floorDiv = Math.CopySign(0.0, a / b);
        }

        return (floorDiv, mod);
    }

    /// <summary>Python <c>a / b</c> for floats: raises on a zero divisor instead of returning infinity.</summary>
    public static double TrueDiv(double a, double b)
    {
        if (b == 0)
        {
            throw new PyZeroDivisionError("division by zero");
        }

        return a / b;
    }

    /// <summary>Python <c>int(x)</c> / <c>math.trunc(x)</c> for a float.</summary>
    public static BigInteger Truncate(double x) => ToInteger(x, Math.Truncate(x));

    /// <summary>Python <c>math.floor(x)</c> for a float (returns an int).</summary>
    public static BigInteger Floor(double x) => ToInteger(x, Math.Floor(x));

    /// <summary>Python <c>math.ceil(x)</c> for a float (returns an int).</summary>
    public static BigInteger Ceil(double x) => ToInteger(x, Math.Ceiling(x));

    /// <summary>Python <c>min(a, b)</c> on floats: <paramref name="a"/> unless <paramref name="b"/> is strictly smaller.</summary>
    public static double Min(double a, double b) => b < a ? b : a;

    /// <summary>Python <c>max(a, b)</c> on floats: <paramref name="a"/> unless <paramref name="b"/> is strictly larger.</summary>
    public static double Max(double a, double b) => b > a ? b : a;

    /// <summary>Python <c>min(iterable)</c> on floats: the first element that no later element is strictly below.</summary>
    public static double Min(IReadOnlyList<double> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        if (values.Count == 0)
        {
            throw new PyValueError("min() iterable argument is empty");
        }

        var best = values[0];
        for (var i = 1; i < values.Count; i++)
        {
            if (values[i] < best)
            {
                best = values[i];
            }
        }

        return best;
    }

    /// <summary>Python <c>max(iterable)</c> on floats: the first element that no later element is strictly above.</summary>
    public static double Max(IReadOnlyList<double> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        if (values.Count == 0)
        {
            throw new PyValueError("max() iterable argument is empty");
        }

        var best = values[0];
        for (var i = 1; i < values.Count; i++)
        {
            if (values[i] > best)
            {
                best = values[i];
            }
        }

        return best;
    }

    private static BigInteger ToInteger(double original, double integral)
    {
        if (double.IsNaN(original))
        {
            throw new PyValueError("cannot convert float NaN to integer");
        }

        if (double.IsInfinity(original))
        {
            throw new PyOverflowError("cannot convert float infinity to integer");
        }

        return new BigInteger(integral);
    }
}
