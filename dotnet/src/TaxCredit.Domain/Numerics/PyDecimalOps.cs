using System.Numerics;
using System.Text.RegularExpressions;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// The arithmetic Python's <c>decimal.Decimal</c> performs under the default context (28 significant digits,
/// <c>ROUND_HALF_EVEN</c>) on the finite values <see cref="PyDecimal"/> holds.
/// </summary>
/// <remarks>
/// Why a layer: <c>+</c>, <c>-</c>, unary <c>-</c>, <c>abs()</c> and <c>sum()</c> on <c>Decimal</c> round every result to 28 digits
/// (so a 30-digit input loses digits the moment it is added) and keep the smaller exponent (so <c>Decimal("140000.00") + Decimal("0")</c>
/// prints with two decimals); comparisons are exact and ignore exponents and the sign of zero. <see cref="decimal"/> does none of this.
/// Not modelled (a <see cref="PyUnsupportedException"/>): NaN and infinities, exponents more than 5,000 apart, exponent overflow.
/// Source: CPython <c>Lib/_pydecimal.py</c> (<c>__add__</c>, <c>__neg__</c>, <c>__abs__</c>, <c>_fix</c>, <c>_cmp</c>).
/// </remarks>
public static partial class PyDecimalOps
{
    private const int MaxExponentGap = 5000;

    /// <summary><c>Decimal("0")</c>: the start value of every <c>sum(..., Decimal("0"))</c>.</summary>
    public static PyDecimal Zero { get; } = new(false, BigInteger.Zero, 0);

    /// <summary>Python <c>Decimal(str(i))</c> for an int: exact, never rounded to the context.</summary>
    public static PyDecimal FromInt(BigInteger value) => new(value.Sign < 0, BigInteger.Abs(value), 0);

    /// <summary>Python <c>Decimal(text)</c> for a finite decimal literal (surrounding whitespace allowed, underscores ignored).</summary>
    /// <exception cref="PyInvalidOperation">With Python's <c>ConversionSyntax</c> message when the text is not a number.</exception>
    /// <exception cref="PyUnsupportedException">For <c>NaN</c>, <c>Infinity</c> and non-ASCII digits, which this port does not model.</exception>
    public static PyDecimal FromString(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        // CPython's C decimal drops every underscore before parsing, so "_1", "1_" and "1__0" are all valid.
        var s = PyStr.Strip(text).Replace("_", string.Empty, StringComparison.Ordinal);
        if (Literal().IsMatch(s))
        {
            return PyDecimal.Parse(s);
        }

        var bare = s.TrimStart('+', '-').ToLowerInvariant();
        if (bare is "nan" or "snan" or "inf" or "infinity" || s.Any(c => c > 127 && char.IsDigit(c)))
        {
            throw new PyUnsupportedException("Decimal NaN, Infinity and non-ASCII digits are not modelled by this port");
        }

        throw new PyInvalidOperation("[<class 'decimal.ConversionSyntax'>]");
    }

    /// <summary>Python <c>a + b</c> under the default context.</summary>
    public static PyDecimal Add(PyDecimal a, PyDecimal b)
    {
        var exponent = Math.Min(a.Exponent, b.Exponent);
        CheckGap(a, b);
        if (a.Coefficient.IsZero && b.Coefficient.IsZero)
        {
            // _pydecimal __add__: the sign of an exact zero is the smaller of the two signs, so only (-0) + (-0) is negative.
            return Fix(a.Negative && b.Negative, BigInteger.Zero, exponent);
        }

        var sum = Signed(a, exponent) + Signed(b, exponent);
        return Fix(sum.Sign < 0, BigInteger.Abs(sum), exponent);
    }

    /// <summary>Python <c>a - b</c>: the sum with the sign of <paramref name="b"/> flipped (also for a zero).</summary>
    public static PyDecimal Subtract(PyDecimal a, PyDecimal b) => Add(a, b with { Negative = !b.Negative });

    /// <summary>Python unary <c>-a</c>: a zero loses its sign under <c>ROUND_HALF_EVEN</c>, and the result is rounded to the context.</summary>
    public static PyDecimal Negate(PyDecimal a) => Fix(!a.Negative && !a.Coefficient.IsZero, a.Coefficient, a.Exponent);

    /// <summary>Python <c>abs(a)</c>: the magnitude, rounded to the context.</summary>
    public static PyDecimal Abs(PyDecimal a) => Fix(false, a.Coefficient, a.Exponent);

    /// <summary>The ordering of two decimals by value: -1, 0 or 1 (zeros of either sign are equal; exponents do not matter).</summary>
    public static int Compare(PyDecimal a, PyDecimal b)
    {
        CheckGap(a, b);
        var exponent = Math.Min(a.Exponent, b.Exponent);
        return Signed(a, exponent).CompareTo(Signed(b, exponent));
    }

    /// <summary>Python <c>sum(items, Decimal("0"))</c>: every partial sum is rounded to the context.</summary>
    public static PyDecimal Sum(IEnumerable<PyDecimal> items)
    {
        ArgumentNullException.ThrowIfNull(items);
        var total = Zero;
        foreach (var item in items)
        {
            total = Add(total, item);
        }

        return total;
    }

    private static BigInteger Signed(PyDecimal d, int exponent)
    {
        var scaled = d.Coefficient * BigInteger.Pow(10, d.Exponent - exponent);
        return d.Negative ? -scaled : scaled;
    }

    private static void CheckGap(PyDecimal a, PyDecimal b)
    {
        if (Math.Abs((long)a.Exponent - b.Exponent) > MaxExponentGap)
        {
            throw new PyUnsupportedException("decimal operands with exponents more than 5,000 apart are not modelled by this port");
        }
    }

    /// <summary>_pydecimal <c>_fix</c>: round the coefficient to 28 digits, half to even (a carry that makes 29 digits drops one more).</summary>
    private static PyDecimal Fix(bool negative, BigInteger coefficient, int exponent)
    {
        var digits = DigitCount(coefficient);
        if (digits <= PyDecimal.ContextPrecision)
        {
            return new PyDecimal(negative, coefficient, exponent);
        }

        var drop = digits - PyDecimal.ContextPrecision;
        var divisor = BigInteger.Pow(10, drop);
        var q = BigInteger.DivRem(coefficient, divisor, out var r);
        var cmp = (r * 2).CompareTo(divisor);
        if (cmp > 0 || (cmp == 0 && !q.IsEven))
        {
            q += 1;
        }

        exponent += drop;
        if (DigitCount(q) > PyDecimal.ContextPrecision)
        {
            q /= 10;
            exponent += 1;
        }

        return new PyDecimal(negative, q, exponent);
    }

    private static int DigitCount(BigInteger value) =>
        value.IsZero ? 1 : value.ToString(System.Globalization.CultureInfo.InvariantCulture).Length;

    [GeneratedRegex(@"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")]
    private static partial Regex Literal();
}
