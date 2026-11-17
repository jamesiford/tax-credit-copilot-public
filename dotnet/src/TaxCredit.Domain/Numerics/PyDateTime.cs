using System.Globalization;
using System.Text.RegularExpressions;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// A Python <c>datetime.datetime</c>: a calendar date, a time of day to the microsecond and, when timezone-aware, a whole-minute UTC offset.
/// </summary>
/// <remarks>
/// Why not <see cref="DateTimeOffset"/>: Python distinguishes naive from aware datetimes and prints microseconds only when they
/// are non-zero, and the claim wire shape is exactly <c>datetime.isoformat()</c>. Sub-minute offsets and <c>fold</c> are not modelled.
/// </remarks>
/// <param name="Date">The calendar date.</param>
/// <param name="Hour">Hour, 0..23.</param>
/// <param name="Minute">Minute, 0..59.</param>
/// <param name="Second">Second, 0..59.</param>
/// <param name="Microsecond">Microsecond, 0..999999.</param>
/// <param name="OffsetMinutes">UTC offset in minutes, or <c>null</c> for a naive datetime.</param>
public readonly partial record struct PyDateTime(DateOnly Date, int Hour, int Minute, int Second, int Microsecond, int? OffsetMinutes)
{
    /// <summary>Python <c>datetime.now(timezone.utc)</c>.</summary>
    public static PyDateTime UtcNow()
    {
        var now = DateTime.UtcNow;
        var micro = (int)(now.Ticks % TimeSpan.TicksPerSecond / 10);
        return new PyDateTime(DateOnly.FromDateTime(now), now.Hour, now.Minute, now.Second, micro, 0);
    }

    /// <summary>Parses the text <see cref="IsoFormat"/> produces (<c>YYYY-MM-DDTHH:MM:SS[.ffffff][+HH:MM]</c>).</summary>
    /// <param name="text">The ISO text.</param>
    /// <exception cref="PyValueError">For any other text or an impossible component.</exception>
    public static PyDateTime FromIsoFormat(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var m = Shape().Match(text);
        if (!m.Success)
        {
            throw new PyValueError($"Invalid isoformat string: '{text}'");
        }

        int Group(int i) => int.Parse(m.Groups[i].Value, CultureInfo.InvariantCulture);
        int? offset = null;
        if (m.Groups[8].Success)
        {
            var minutes = (Group(9) * 60) + Group(10);
            offset = m.Groups[8].Value == "-" ? -minutes : minutes;
        }

        var micro = m.Groups[7].Success ? Group(7) : 0;
        if (Group(4) > 23 || Group(5) > 59 || Group(6) > 59)
        {
            throw new PyValueError("hour must be in 0..23");
        }

        return new PyDateTime(PyDate.Make(Group(1), Group(2), Group(3)), Group(4), Group(5), Group(6), micro, offset);
    }

    /// <summary>Python <c>dt.isoformat()</c>.</summary>
    /// <returns>The ISO 8601 text, with microseconds only when non-zero and the offset only when aware.</returns>
    public string IsoFormat()
    {
        var text = string.Create(CultureInfo.InvariantCulture, $"{Date.Year:D4}-{Date.Month:D2}-{Date.Day:D2}T{Hour:D2}:{Minute:D2}:{Second:D2}");
        if (Microsecond != 0)
        {
            text += string.Create(CultureInfo.InvariantCulture, $".{Microsecond:D6}");
        }

        if (OffsetMinutes is { } offset)
        {
            var abs = Math.Abs(offset);
            text += string.Create(CultureInfo.InvariantCulture, $"{(offset < 0 ? '-' : '+')}{abs / 60:D2}:{abs % 60:D2}");
        }

        return text;
    }

    [GeneratedRegex(@"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d{6}))?(?:([+-])(\d\d):(\d\d))?$")]
    private static partial Regex Shape();
}
