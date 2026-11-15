namespace TaxCredit.Domain.Numerics;

/// <summary>Python <c>datetime.date</c> / <c>calendar</c> behaviour over <see cref="DateOnly"/>.</summary>
/// <remarks>
/// Why a layer: .NET reports invalid dates as <see cref="ArgumentOutOfRangeException"/> and has no
/// <c>replace()</c> or <c>monthrange()</c>; Python raises <c>ValueError</c> / <c>OverflowError</c> and the engine
/// relies on those distinctions (a bad measuring day is clamped, a bad date row is skipped). Python's
/// <c>date.fromisoformat</c> (3.11+) also accepts <c>YYYYMMDD</c> and ISO week dates, and nothing else, whereas
/// <see cref="DateOnly.Parse(string)"/> accepts dozens of culture-dependent shapes.
/// Source: CPython <c>Modules/_datetimemodule.c</c>, <c>Lib/calendar.py</c>.
/// </remarks>
public static class PyDate
{
    /// <summary>Python <c>calendar.isleap(year)</c>.</summary>
    public static bool IsLeap(int year) => year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);

    /// <summary>Python <c>calendar.monthrange(year, month)</c>: (weekday of the 1st with Monday = 0, days in month).</summary>
    public static (int FirstWeekday, int Days) MonthRange(int year, int month)
    {
        if (month is < 1 or > 12)
        {
            throw new PyValueError($"bad month number {month}; must be 1-12");
        }

        var first = Make(year, month, 1);
        return (Weekday(first), DateTime.DaysInMonth(year, month));
    }

    /// <summary>Python <c>date(year, month, day)</c>.</summary>
    /// <exception cref="PyValueError">When the components do not form a valid date.</exception>
    public static DateOnly Make(int year, int month, int day)
    {
        if (year is < 1 or > 9999)
        {
            throw new PyValueError($"year {year} is out of range");
        }

        if (month is < 1 or > 12)
        {
            throw new PyValueError("month must be in 1..12");
        }

        if (day < 1 || day > DateTime.DaysInMonth(year, month))
        {
            throw new PyValueError("day is out of range for month");
        }

        return new DateOnly(year, month, day);
    }

    /// <summary>Python <c>d.replace(year=..., month=..., day=...)</c>.</summary>
    public static DateOnly Replace(DateOnly d, int? year = null, int? month = null, int? day = null) =>
        Make(year ?? d.Year, month ?? d.Month, day ?? d.Day);

    /// <summary>Python <c>d + timedelta(days=n)</c>.</summary>
    /// <exception cref="PyOverflowError">When the result leaves 0001-01-01..9999-12-31.</exception>
    public static DateOnly AddDays(DateOnly d, int days)
    {
        var ordinal = (long)d.DayNumber + days;
        if (ordinal < DateOnly.MinValue.DayNumber || ordinal > DateOnly.MaxValue.DayNumber)
        {
            throw new PyOverflowError("date value out of range");
        }

        return DateOnly.FromDayNumber((int)ordinal);
    }

    /// <summary>Python <c>d.isoweekday()</c> (Monday = 1 .. Sunday = 7).</summary>
    public static int IsoWeekday(DateOnly d) => d.DayOfWeek == DayOfWeek.Sunday ? 7 : (int)d.DayOfWeek;

    /// <summary>Python <c>d.weekday()</c> (Monday = 0 .. Sunday = 6).</summary>
    public static int Weekday(DateOnly d) => IsoWeekday(d) - 1;

    /// <summary>Python <c>d.toordinal()</c> (0001-01-01 = 1).</summary>
    public static int ToOrdinal(DateOnly d) => d.DayNumber + 1;

    /// <summary>Python <c>tuple(d.isocalendar())</c>: (ISO year, ISO week, ISO weekday).</summary>
    public static (int Year, int Week, int Day) IsoCalendar(DateOnly d)
    {
        var weekday = IsoWeekday(d);
        var year = d.Year;
        var week1Monday = Week1Monday(year);
        if (d.DayNumber < week1Monday.DayNumber)
        {
            year--;
            week1Monday = Week1Monday(year);
        }
        else if (year < 9999 && d.DayNumber >= Week1Monday(year + 1).DayNumber)
        {
            year++;
            week1Monday = Week1Monday(year);
        }

        return (year, ((d.DayNumber - week1Monday.DayNumber) / 7) + 1, weekday);
    }

    /// <summary>Python <c>date.fromisoformat(text)</c> (3.11+ formats: calendar and week dates, basic and extended).</summary>
    /// <remarks>
    /// CPython 3.12 gates on the UTF-8 BYTE length (7, 8 or 10) and then parses the leading components without requiring that the whole text was consumed, so
    /// <c>"20230101.0"</c> and <c>"2023W011xx"</c> are dates and a lone surrogate is "invalid". The message quotes the text with <c>repr</c>.
    /// </remarks>
    /// <exception cref="PyValueError">For any other text.</exception>
    public static DateOnly FromIsoFormat(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (!TryFromIsoFormat(text, out var result))
        {
            // CPython validates the components of a well-formed calendar date in the date constructor, so an impossible
            // month or day raises that constructor's message, not "Invalid isoformat string" (found by the proximity family).
            if (TryCalendarParts(text, out var y, out var m, out var d))
            {
                Make(y, m, d);
            }

            throw new PyValueError($"Invalid isoformat string: {PyStr.Repr(text)}");
        }

        return result;
    }

    /// <summary>The year, month and day of a syntactically valid calendar date (<c>YYYY-MM-DD</c> or <c>YYYYMMDD</c>) whose values may be impossible.</summary>
    private static bool TryCalendarParts(string text, out int year, out int month, out int day)
    {
        (year, month, day) = (0, 0, 0);
        if (!HasIsoLength(text))
        {
            return false;
        }

        var p = 0;
        if (!Digits(text, ref p, 4, out year))
        {
            return false;
        }

        var separator = At(text, p) == '-';
        if (separator)
        {
            p++;
        }

        if (At(text, p) == 'W' || !Digits(text, ref p, 2, out month) || (separator && At(text, p++) != '-'))
        {
            return false;
        }

        return Digits(text, ref p, 2, out day);
    }

    /// <summary>Non-throwing form of <see cref="FromIsoFormat"/>.</summary>
    public static bool TryFromIsoFormat(string text, out DateOnly result)
    {
        ArgumentNullException.ThrowIfNull(text);
        result = default;
        if (!HasIsoLength(text, out var length))
        {
            return false;
        }

        var p = 0;
        if (!Digits(text, ref p, 4, out var year))
        {
            return false;
        }

        var separator = At(text, p) == '-';
        if (separator)
        {
            p++;
        }

        if (At(text, p) == 'W')
        {
            return TryParseWeekDate(text, length, p + 1, separator, year, out result);
        }

        if (!TryCalendarParts(text, out year, out var month, out var day))
        {
            return false;
        }

        if (year < 1 || month is < 1 or > 12 || day < 1 || day > DateTime.DaysInMonth(year, month))
        {
            return false;
        }

        result = new DateOnly(year, month, day);
        return true;
    }

    private static bool TryParseWeekDate(string text, int length, int p, bool separator, int year, out DateOnly result)
    {
        result = default;
        if (!Digits(text, ref p, 2, out var week))
        {
            return false;
        }

        var day = 1;
        if (p < length)
        {
            if (separator)
            {
                if (At(text, p) != '-')
                {
                    return false;
                }

                p++;
            }

            if (!Digits(text, ref p, 1, out day))
            {
                return false;
            }
        }

        if (year < 1 || week is < 1 or > 53 || day is < 1 or > 7)
        {
            return false;
        }

        if (week == 53 && IsoWeeksInYear(year) != 53)
        {
            return false;
        }

        var ordinal = (long)Week1Monday(year).DayNumber + ((week - 1) * 7) + (day - 1);
        if (ordinal > DateOnly.MaxValue.DayNumber)
        {
            return false;
        }

        result = DateOnly.FromDayNumber((int)ordinal);
        return true;
    }

    private static bool HasIsoLength(string text) => HasIsoLength(text, out _);

    /// <summary>CPython's gate: the UTF-8 length is 7, 8 or 10; text with a lone surrogate has no UTF-8 form and is not a date.</summary>
    private static bool HasIsoLength(string text, out int length)
    {
        length = 0;
        try
        {
            length = new System.Text.UTF8Encoding(false, true).GetByteCount(text);
        }
        catch (System.Text.EncoderFallbackException)
        {
            return false;
        }

        return length is 7 or 8 or 10;
    }

    /// <summary>The character at <paramref name="p"/>, or NUL past the end (CPython reads the string's terminator).</summary>
    private static char At(string text, int p) => p < text.Length ? text[p] : '\0';

    private static bool Digits(string text, ref int p, int count, out int value)
    {
        value = 0;
        if (p + count > text.Length)
        {
            return false;
        }

        for (var i = 0; i < count; i++)
        {
            var c = text[p + i];
            if (c is < '0' or > '9')
            {
                return false;
            }

            value = (value * 10) + (c - '0');
        }

        p += count;
        return true;
    }

    private static DateOnly Week1Monday(int year)
    {
        var jan4 = new DateOnly(Math.Clamp(year, 1, 9999), 1, 4);
        return DateOnly.FromDayNumber(jan4.DayNumber - (IsoWeekday(jan4) - 1));
    }

    private static int IsoWeeksInYear(int year)
    {
        var next = year >= 9999 ? DateOnly.MaxValue.DayNumber + 1 : Week1Monday(year + 1).DayNumber;
        return (next - Week1Monday(year).DayNumber) / 7;
    }
}
