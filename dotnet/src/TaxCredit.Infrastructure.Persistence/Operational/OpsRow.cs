using System.Globalization;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

internal sealed class OpsRow(IReadOnlyDictionary<string, object?> values)
{
    internal object? this[string key] => values.TryGetValue(key, out var value) && value is not DBNull ? value : null;
    internal string? Text(string key) => this[key] switch
    {
        null => null,
        DateTime or DateTimeOffset => ParseInstant(this[key])?.IsoFormat(),
        _ => Convert.ToString(this[key], CultureInfo.InvariantCulture),
    };
    internal string Required(string key) => Text(key) ?? throw new InvalidDataException($"Missing operational column {key}.");
    internal long Long(string key) => Convert.ToInt64(this[key], CultureInfo.InvariantCulture);
    internal long? OptionalLong(string key) => this[key] is null ? null : Long(key);
    internal double? Number(string key) => this[key] is null ? null : Convert.ToDouble(this[key], CultureInfo.InvariantCulture);
    internal bool Bool(string key) => this[key] is not null && Convert.ToBoolean(this[key], CultureInfo.InvariantCulture);
    internal PyDict? Document(string key) => Text(key) is { } text ? (PyDict)PyJson.Loads(text)! : null;
    internal PyDateTime? Instant(string key) => ParseInstant(this[key]);
    internal DateOnly? Day(string key) => this[key] switch
    {
        null => null,
        DateOnly day => day,
        DateTime date => DateOnly.FromDateTime(date),
        _ => DateOnly.ParseExact(Required(key)[..10], "yyyy-MM-dd", CultureInfo.InvariantCulture),
    };

    internal static PyDateTime? ParseInstant(object? value)
    {
        if (value is null or DBNull)
        {
            return null;
        }

        if (value is PyDateTime instant)
        {
            return instant;
        }

        var text = value switch
        {
            DateTime date => date.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff", CultureInfo.InvariantCulture) + "+00:00",
            DateTimeOffset date => date.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffffzzz", CultureInfo.InvariantCulture),
            DateOnly date => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
            _ => Convert.ToString(value, CultureInfo.InvariantCulture)!,
        };
        if (text.Length == 10)
        {
            text += "T00:00:00";
        }

        text = text.Replace(' ', 'T');
        if (text.EndsWith('Z'))
        {
            text = text[..^1] + "+00:00";
        }

        var dot = text.IndexOf('.', StringComparison.Ordinal);
        if (dot >= 0)
        {
            var end = dot + 1;
            while (end < text.Length && char.IsAsciiDigit(text[end]))
            {
                end++;
            }

            text = text[..(dot + 1)] + text[(dot + 1)..end].PadRight(6, '0')[..6] + text[end..];
        }

        return PyDateTime.FromIsoFormat(text);
    }

    // Keep SQLite's authored text; DATETIME2 requires typed UTC instants rather than offset-bearing string conversions.
    internal static object? Timestamp(SqlSession session, PyDateTime? value) =>
        session.Dialect is SqliteDialect ? value?.IsoFormat() : value;

    internal static object? Timestamp(SqlSession session, string value) =>
        session.Dialect is SqliteDialect ? value : ParseInstant(value);

    internal static object? EffectiveDate(SqlSession session, PyDateTime? value) =>
        session.Dialect is SqliteDialect ? value?.IsoFormat() : value?.Date;

    internal static object? Clock(SqlSession session, PyDateTime? value) =>
        value is { } instant ? session.Dialect is SqliteDialect ? Clock(instant) : ParseInstant(Clock(instant)) : null;

    internal static string? Json(PyDict? document) => document is null ? null : PyJson.Dumps(document);
    internal static string Clock(DateTimeOffset now) => now.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff", CultureInfo.InvariantCulture) + "+00:00";
    internal static string Clock(PyDateTime now)
    {
        var date = now.Date.ToDateTime(new TimeOnly(now.Hour, now.Minute, now.Second)).AddTicks(now.Microsecond * 10L);
        return Clock(new DateTimeOffset(date, TimeSpan.FromMinutes(now.OffsetMinutes ?? 0)));
    }

    internal static PyDateTime AddSeconds(PyDateTime instant, int seconds)
    {
        var date = instant.Date.ToDateTime(new TimeOnly(instant.Hour, instant.Minute, instant.Second)).AddTicks(instant.Microsecond * 10L);
        return ParseInstant(Clock(new DateTimeOffset(date, TimeSpan.FromMinutes(instant.OffsetMinutes ?? 0)).AddSeconds(seconds)))!.Value;
    }
}
