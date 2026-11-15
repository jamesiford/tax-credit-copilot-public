using System.Globalization;
using System.Numerics;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>The two <c>decimal</c> rounding modes the engine uses.</summary>
public enum PyRoundingMode
{
    /// <summary><c>ROUND_HALF_UP</c>: ties round away from zero.</summary>
    HalfUp,

    /// <summary><c>ROUND_HALF_EVEN</c>: ties round to the even neighbour.</summary>
    HalfEven,
}

/// <summary>
/// A finite Python <c>decimal.Decimal</c> (sign, integer coefficient, power-of-ten exponent) under the default
/// context (28 significant digits). Only what the engine needs: construction from <c>str(float)</c>,
/// <c>quantize</c>, <c>str()</c> and <c>float()</c>.
/// </summary>
/// <remarks>
/// Why not <see cref="decimal"/>: <c>System.Decimal</c> holds at most 28-29 digits with a scale of 0..28 and has
/// no notion of trailing-zero-preserving exponents, so <c>Decimal("1E+22")</c>, <c>Decimal("100.0")</c> and the
/// <c>InvalidOperation</c> raised when a quantized result needs more than 28 digits cannot be reproduced.
/// <c>(decimal)someDouble</c> is worse: it keeps only ~15 significant digits.
/// </remarks>
/// <param name="Negative">The sign (kept for zero: <c>Decimal("-0.00")</c> is a negative zero).</param>
/// <param name="Coefficient">Non-negative integer coefficient.</param>
/// <param name="Exponent">Power of ten applied to the coefficient.</param>
public readonly record struct PyDecimal(bool Negative, BigInteger Coefficient, int Exponent)
{
    /// <summary>Default decimal context precision (<c>decimal.getcontext().prec</c>).</summary>
    public const int ContextPrecision = 28;

    /// <summary><c>Decimal(str(x))</c>: the exact decimal of the shortest round-trip repr of a finite double.</summary>
    public static PyDecimal FromFloatViaStr(double x)
    {
        if (!double.IsFinite(x))
        {
            throw new PyInvalidOperation("non-finite values are not supported by this port");
        }

        return Parse(PyFloat.Repr(x));
    }

    /// <summary>Parses the plain/exponent decimal text produced by Python's <c>repr(float)</c> or <see cref="ToString"/>.</summary>
    public static PyDecimal Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var s = text;
        var negative = false;
        if (s.StartsWith('-'))
        {
            negative = true;
            s = s[1..];
        }
        else if (s.StartsWith('+'))
        {
            s = s[1..];
        }

        var exp = 0;
        var e = s.IndexOfAny(['e', 'E']);
        if (e >= 0)
        {
            exp = int.Parse(s.AsSpan(e + 1), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
            s = s[..e];
        }

        var dot = s.IndexOf('.', StringComparison.Ordinal);
        if (dot >= 0)
        {
            exp -= s.Length - dot - 1;
            s = s.Remove(dot, 1);
        }

        return new PyDecimal(negative, BigInteger.Parse(s, NumberStyles.None, CultureInfo.InvariantCulture), exp);
    }

    /// <summary>Python <c>d.quantize(Decimal(1).scaleb(-places), rounding=mode)</c>.</summary>
    /// <exception cref="PyInvalidOperation">When the result needs more than 28 digits.</exception>
    public PyDecimal Quantize(int places, PyRoundingMode mode)
    {
        var target = -places;
        BigInteger coefficient;
        if (Exponent >= target)
        {
            coefficient = Coefficient * BigInteger.Pow(10, Exponent - target);
        }
        else
        {
            var divisor = BigInteger.Pow(10, target - Exponent);
            var q = BigInteger.DivRem(Coefficient, divisor, out var r);
            var cmp = (r * 2).CompareTo(divisor);
            var up = mode switch
            {
                PyRoundingMode.HalfUp => cmp >= 0,
                PyRoundingMode.HalfEven => cmp > 0 || (cmp == 0 && !q.IsEven),
                _ => throw new ArgumentOutOfRangeException(nameof(mode)),
            };
            coefficient = up ? q + 1 : q;
        }

        if (DigitCount(coefficient) > ContextPrecision)
        {
            throw new PyInvalidOperation("quantize result has too many digits for the context precision");
        }

        return new PyDecimal(Negative, coefficient, target);
    }

    /// <summary>Python <c>float(d)</c>: the nearest double to the decimal's text.</summary>
    public double ToDouble() => double.Parse(ToString(), NumberStyles.Float, CultureInfo.InvariantCulture);

    /// <summary>Python <c>str(d)</c> (scientific form only when the exponent is positive or adjusted below -6).</summary>
    public override string ToString()
    {
        var digits = Coefficient.ToString(CultureInfo.InvariantCulture);
        var leftDigits = Exponent + digits.Length;
        var dotPlace = Exponent <= 0 && leftDigits > -6 ? leftDigits : 1;
        string intPart;
        string fracPart;
        if (dotPlace <= 0)
        {
            intPart = "0";
            fracPart = "." + new string('0', -dotPlace) + digits;
        }
        else if (dotPlace >= digits.Length)
        {
            intPart = digits + new string('0', dotPlace - digits.Length);
            fracPart = string.Empty;
        }
        else
        {
            intPart = digits[..dotPlace];
            fracPart = "." + digits[dotPlace..];
        }

        var expPart = leftDigits == dotPlace
            ? string.Empty
            : "E" + (leftDigits - dotPlace).ToString("+0;-0", CultureInfo.InvariantCulture);
        return new StringBuilder().Append(Negative ? "-" : string.Empty).Append(intPart).Append(fracPart).Append(expPart).ToString();
    }

    private static int DigitCount(BigInteger value) =>
        value.IsZero ? 1 : value.ToString(CultureInfo.InvariantCulture).Length;
}
