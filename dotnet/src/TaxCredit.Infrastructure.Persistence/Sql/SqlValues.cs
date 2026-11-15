using System.Data;
using System.Data.Common;
using System.Globalization;
using System.Numerics;
using Microsoft.Data.SqlClient;
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
                if (parameter is not SqlParameter sqlParameter)
                {
                    parameter.DbType = DbType.Decimal;
                    parameter.Value = decimal.Parse(number.ToString(), NumberStyles.Float, CultureInfo.InvariantCulture);
                    break;
                }

                var scale = Math.Max(0, -number.Exponent);
                sqlParameter.SqlDbType = SqlDbType.Decimal;
                sqlParameter.Scale = checked((byte)scale);
                sqlParameter.Precision = checked((byte)Math.Max(scale, number.Coefficient.ToString(CultureInfo.InvariantCulture).Length));
                sqlParameter.Value = System.Data.SqlTypes.SqlDecimal.Parse(number.ToString());
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

    internal static DateTime ToUtc(PyDateTime time)
    {
        var date = time.Date.ToDateTime(new TimeOnly(time.Hour, time.Minute, time.Second)).AddTicks(time.Microsecond * 10L);
        return time.OffsetMinutes is { } offset ? DateTime.SpecifyKind(date.AddMinutes(-offset), DateTimeKind.Utc) : date;
    }
}
