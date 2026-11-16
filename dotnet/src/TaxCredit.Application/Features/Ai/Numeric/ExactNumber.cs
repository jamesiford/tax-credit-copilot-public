using System.Globalization;
using System.Numerics;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.Ai.Numeric;

internal static partial class ExactNumber
{
    internal static PyDecimal Parse(string text) => Normalize(PyDecimal.Parse(text));

    internal static PyDecimal Normalize(PyDecimal value)
    {
        if (value.Coefficient.IsZero)
        {
            return PyDecimalOps.Zero;
        }

        while (value.Coefficient % 10 == 0)
        {
            value = value with { Coefficient = value.Coefficient / 10, Exponent = value.Exponent + 1 };
        }

        return value;
    }

    internal static string Plain(PyDecimal value)
    {
        value = Normalize(value);
        var digits = value.Coefficient.ToString(CultureInfo.InvariantCulture);
        var point = digits.Length + value.Exponent;
        var body = point <= 0 ? "0." + new string('0', -point) + digits
            : point >= digits.Length ? digits + new string('0', point - digits.Length)
            : digits.Insert(point, ".");
        return (value.Negative ? "-" : "") + body;
    }

    internal static PyDecimal Scale(PyDecimal value, int power) =>
        Normalize(value with { Exponent = checked(value.Exponent + power) });

    internal static bool TryParse(string text, out PyDecimal value, bool exponent = false)
    {
        value = default;
        if (!(exponent ? Scientific() : Literal()).IsMatch(text.Trim()))
        {
            return false;
        }

        try
        {
            value = Parse(text.Trim());
            return Math.Abs((long)value.Exponent) <= 5000;
        }
        catch (Exception exception) when (exception is FormatException or OverflowException)
        {
            return false;
        }
    }

    internal static BigInteger Distance(PyDecimal left, PyDecimal right, int exponent)
    {
        var a = left.Coefficient * BigInteger.Pow(10, left.Exponent - exponent);
        var b = right.Coefficient * BigInteger.Pow(10, right.Exponent - exponent);
        return BigInteger.Abs((left.Negative ? -a : a) - (right.Negative ? -b : b));
    }

    [GeneratedRegex(@"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")]
    private static partial Regex Literal();

    [GeneratedRegex(@"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")]
    private static partial Regex Scientific();
}
