using System.Data;
using System.Data.Common;
using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Persistence.Sql;

internal static class SqlValues
{
    internal static object? Unwrap(object? value) => value is GoldCell cell ? cell.Kind switch
    {
        GoldKind.DecimalNaN => throw new InvalidOperationException("Non-finite Gold value cannot be stored."),
        _ => cell.Value,
    } : value;

    internal static void Bind(DbParameter parameter, object? value, bool sqlite)
    {
        value = Unwrap(value);
        switch (value)
        {
            case null:
                parameter.Value = DBNull.Value;
                break;
            case BigInteger integer:
                parameter.DbType = DbType.Int64;
                parameter.Value = checked((long)integer);
                break;
            case PyDecimal number when !sqlite:
                var literal = DecimalLiteral(number);
                parameter.DbType = DbType.Decimal;
                parameter.Scale = literal.Scale;
                parameter.Precision = literal.Precision;
                parameter.Value = System.Data.SqlTypes.SqlDecimal.Parse(literal.Text);
                break;
            case PyDecimal number:
                parameter.DbType = DbType.String;
                parameter.Value = number.ToString();
                break;
            case DateOnly day:
                parameter.DbType = sqlite ? DbType.String : DbType.Date;
                parameter.Value = sqlite ? day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) : day.ToDateTime(TimeOnly.MinValue);
                break;
            case PyDateTime time:
                parameter.DbType = sqlite ? DbType.String : DbType.DateTime2;
                parameter.Value = sqlite ? time.IsoFormat().Replace('T', ' ') : ToUtc(time);
                break;
            default:
                parameter.Value = value;
                break;
        }
    }

    private static (string Text, byte Scale, byte Precision) DecimalLiteral(PyDecimal number)
    {
        if (number.Exponent is < -38 or > 38)
        {
            throw new InvalidOperationException("Decimal parameter exceeds SQL Server precision or scale.");
        }

        var digits = number.Coefficient.ToString(CultureInfo.InvariantCulture);
        var scale = Math.Max(0, -number.Exponent);
        var precision = Math.Max(scale, digits.Length + Math.Max(0, number.Exponent));
        if (precision > 38 || scale > 38)
        {
            throw new InvalidOperationException("Decimal parameter exceeds SQL Server precision or scale.");
        }

        if (number.Exponent > 0)
        {
            digits += new string('0', number.Exponent);
        }
        else if (scale > 0)
        {
            digits = digits.PadLeft(scale + 1, '0');
            digits = digits.Insert(digits.Length - scale, ".");
        }

        return ((number.Negative ? "-" : string.Empty) + digits, (byte)scale, (byte)precision);
    }

    internal static DateTime ToUtc(PyDateTime time)
    {
        var date = time.Date.ToDateTime(new TimeOnly(time.Hour, time.Minute, time.Second)).AddTicks(time.Microsecond * 10L);
        return time.OffsetMinutes is { } offset ? DateTime.SpecifyKind(date.AddMinutes(-offset), DateTimeKind.Utc) : date;
    }
}
