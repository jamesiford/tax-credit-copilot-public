using System.Globalization;
using System.Numerics;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>A non-finite <c>decimal.Decimal</c> (<c>NaN</c>, <c>sNaN</c>, <c>Infinity</c>) as an input value; <see cref="PyDecimal"/> holds only finite ones.</summary>
/// <param name="Text">What <c>str()</c> shows, for example <c>NaN</c>, <c>-NaN</c>, <c>NaN12</c>, <c>sNaN</c>, <c>-Infinity</c>.</param>
public sealed record PyDecimalSpecial(string Text);

/// <summary>
/// The four value coercions of <c>tools/gold_projection.py</c> (<c>_dec</c>, <c>_day</c>, <c>_flag</c> and the <c>int()</c>, <c>str()</c> and truthiness
/// the row builders apply to loosely typed input). Inputs are the values a Python row can hold: <c>null</c>, <c>bool</c>, <c>long</c>,
/// <see cref="BigInteger"/>, <c>double</c>, <c>string</c>, <see cref="PyDecimal"/>, <see cref="PyDecimalSpecial"/>, <see cref="DateOnly"/>, <see cref="PyDateTime"/>.
/// </summary>
public static partial class GoldValues
{
    private const string InvalidOperation = "[<class 'decimal.InvalidOperation'>]";

    /// <summary>Python <c>_dec(value, places)</c>: <c>None</c> and <c>""</c> are <c>None</c>, anything else <c>Decimal(str(value)).quantize(0.01 or 0.0001)</c> under the default context.</summary>
    /// <remarks>
    /// Why through <c>str</c>: a float 0.1 becomes exactly <c>Decimal("0.1")</c>, not its 55-digit binary expansion. A bool, a date or a list stringifies to
    /// text that is never a number (<c>ConversionSyntax</c>); an infinity, a signalling NaN or a result of more than 28 digits is <c>InvalidOperation</c>; a quiet NaN
    /// quantizes to itself (so it reaches the row as a NaN cell, exactly as Python would hand it to the driver).
    /// </remarks>
    /// <param name="value">The input.</param>
    /// <param name="places">2 or 4 (the only keys of Python's <c>_QUANTIZERS</c>).</param>
    /// <returns>A decimal cell, a NaN cell or <see cref="GoldCell.Null"/>.</returns>
    /// <exception cref="PyInvalidOperation">With CPython's message for the signal raised.</exception>
    public static GoldCell Dec(object? value, int places = 2)
    {
        if (places is not (2 or 4))
        {
            throw new ArgumentOutOfRangeException(nameof(places));
        }

        if (value is null or string { Length: 0 })
        {
            return GoldCell.Null;
        }

        if (value is IReadOnlyList<object?> or PyDict)
        {
            // str() of a container is its repr, which is never a number.
            throw new PyInvalidOperation("[<class 'decimal.ConversionSyntax'>]");
        }

        var text = Str(value);
        var special = Special().Match(PyStr.Strip(text));
        if (special.Success)
        {
            return SpecialCell(special);
        }

        var parsed = PyDecimalOps.FromString(text);
        try
        {
            return GoldCell.OfDecimal(parsed.Quantize(places, PyRoundingMode.HalfEven));
        }
        catch (PyInvalidOperation)
        {
            throw new PyInvalidOperation(InvalidOperation);
        }
    }

    /// <summary>Python <c>_day(value)</c>: <c>None</c> and <c>""</c> are <c>None</c>, a date stays, a datetime becomes its date, anything else is <c>date.fromisoformat(str(value)[:10])</c>.</summary>
    /// <param name="value">The input.</param>
    /// <returns>A date cell or <see cref="GoldCell.Null"/>.</returns>
    /// <exception cref="PyValueError">When the text is not an ISO date.</exception>
    public static GoldCell Day(object? value) => value switch
    {
        null or string { Length: 0 } => GoldCell.Null,
        DateOnly d => GoldCell.OfDate(d),
        PyDateTime t => GoldCell.OfDate(t.Date),
        _ => GoldCell.OfDate(PyDate.FromIsoFormat(PyStr.Prefix(Str(value), 10))),
    };

    /// <summary>Python <c>_flag(value)</c>: 1 when truthy, else 0 (the driver wants an int for a <c>BIT</c>).</summary>
    /// <param name="value">The input.</param>
    /// <returns>An int cell.</returns>
    public static GoldCell Flag(object? value) => GoldCell.OfInt(Truthy(value) ? 1 : 0);

    /// <summary>Python truthiness of a row value (a NaN float and a NaN Decimal are truthy; <c>Decimal("-0.00")</c> is not).</summary>
    /// <param name="value">The value.</param>
    /// <returns>Whether <c>bool(value)</c> is true.</returns>
    public static bool Truthy(object? value) => value switch
    {
        null => false,
        bool b => b,
        long l => l != 0,
        BigInteger b => !b.IsZero,
        double d => d != 0.0,
        string s => s.Length > 0,
        PyDecimal d => !d.Coefficient.IsZero,
        IReadOnlyList<object?> list => list.Count > 0,
        PyDict dict => dict.Count > 0,
        _ => true,
    };

    /// <summary>Python <c>str(value)</c> for the value types a row holds (a datetime uses a space, not <c>T</c>).</summary>
    /// <param name="value">The value.</param>
    /// <returns>The text.</returns>
    /// <exception cref="PyUnsupportedException">For a type a payroll row never holds.</exception>
    public static string Str(object? value) => value switch
    {
        null => "None",
        string s => s,
        bool b => b ? "True" : "False",
        long l => l.ToString(CultureInfo.InvariantCulture),
        BigInteger b => b.ToString(CultureInfo.InvariantCulture),
        double d => PyFloat.Repr(d),
        PyDecimal d => d.ToString(),
        PyDecimalSpecial s => s.Text,
        DateOnly d => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
        PyDateTime t => string.Concat(t.IsoFormat().AsSpan(0, 10), " ", t.IsoFormat().AsSpan(11)),
        _ => throw new PyUnsupportedException("str() of " + value.GetType().Name + " is not modelled"),
    };

    /// <summary>The Python type name of a value, as it appears in <c>TypeError</c> messages.</summary>
    /// <param name="value">The value.</param>
    /// <returns>The name.</returns>
    public static string TypeName(object? value) => value switch
    {
        null => "NoneType",
        string => "str",
        bool => "bool",
        long or BigInteger => "int",
        double => "float",
        PyDecimal or PyDecimalSpecial => "Decimal",
        DateOnly => "date",
        PyDateTime => "datetime",
        IReadOnlyList<object?> => "list",
        PyDict => "dict",
        _ => value.GetType().Name,
    };

    /// <summary>Python <c>int(value)</c> for the types a row holds (floats and Decimals truncate toward zero; text follows <c>int(str)</c>).</summary>
    /// <param name="value">The value (never <c>null</c>: the caller guards it).</param>
    /// <returns>The integer.</returns>
    /// <exception cref="PyValueError">For text that is not an integer, or a NaN.</exception>
    /// <exception cref="PyOverflowError">For an infinity.</exception>
    /// <exception cref="PyTypeError">For a type <c>int()</c> does not take.</exception>
    public static BigInteger ToInt(object? value)
    {
        switch (value)
        {
            case bool b:
                return b ? BigInteger.One : BigInteger.Zero;
            case long l:
                return l;
            case BigInteger big:
                return big;
            case double d when double.IsNaN(d):
                throw new PyValueError("cannot convert float NaN to integer");
            case double d when double.IsInfinity(d):
                throw new PyOverflowError("cannot convert float infinity to integer");
            case double d:
                return new BigInteger(Math.Truncate(d));
            case PyDecimal dec:
                return DecimalToInt(dec);
            case PyDecimalSpecial s:
                throw s.Text.Contains("Inf", StringComparison.Ordinal)
                    ? new PyOverflowError("cannot convert Infinity to integer")
                    : new PyValueError("cannot convert NaN to integer");
            case string text:
                return PyInt.TryParse(text, out var parsed)
                    ? parsed
                    : throw new PyValueError("invalid literal for int() with base 10: " + PyStr.Repr(text));
            default:
                throw new PyTypeError($"int() argument must be a string, a bytes-like object or a real number, not '{TypeName(value)}'");
        }
    }

    private static BigInteger DecimalToInt(PyDecimal d)
    {
        var magnitude = d.Exponent >= 0
            ? d.Coefficient * BigInteger.Pow(10, d.Exponent)
            : BigInteger.Divide(d.Coefficient, BigInteger.Pow(10, -d.Exponent));
        return d.Negative ? -magnitude : magnitude;
    }

    private static GoldCell SpecialCell(Match m)
    {
        if (m.Groups[2].Success || string.Equals(m.Groups[3].Value, "snan", StringComparison.OrdinalIgnoreCase))
        {
            throw new PyInvalidOperation(InvalidOperation);
        }

        var payload = m.Groups[4].Value.TrimStart('0');
        return GoldCell.OfNaN((m.Groups[1].Value == "-" ? "-" : string.Empty) + "NaN" + payload);
    }

    [GeneratedRegex(@"^([+-]?)(?:(inf|infinity)|(snan|nan)([0-9]*))$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex Special();
}
