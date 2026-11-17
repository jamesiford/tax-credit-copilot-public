using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>The Python type of a value in a Gold row: the type is part of the contract, because the driver binds by it.</summary>
public enum GoldKind
{
    /// <summary>Python <c>None</c> (SQL <c>NULL</c>).</summary>
    Null,

    /// <summary>A Python <c>int</c> (also what <c>_flag</c> returns for a <c>BIT</c>).</summary>
    WholeNumber,

    /// <summary>A finite <c>decimal.Decimal</c>.</summary>
    ExactDecimal,

    /// <summary>A <c>decimal.Decimal</c> NaN (<c>Decimal("nan").quantize(...)</c> is a NaN, not an error).</summary>
    DecimalNaN,

    /// <summary>A <c>str</c>.</summary>
    Text,

    /// <summary>A <c>datetime.date</c>.</summary>
    Date,

    /// <summary>A <c>datetime.datetime</c>.</summary>
    DateTime,
}

/// <summary>
/// One typed value of a Gold row. There is deliberately no float kind: <c>gold_projection.py</c> turns every number into a
/// <c>Decimal</c> or an <c>int</c>, so a float reaching a row would be a defect the parity test must see.
/// </summary>
public readonly record struct GoldCell
{
    private GoldCell(GoldKind kind, object? value)
    {
        Kind = kind;
        Value = value;
    }

    /// <summary>The Python type of the value.</summary>
    public GoldKind Kind { get; }

    /// <summary>The boxed value (<see cref="BigInteger"/>, <see cref="PyDecimal"/>, <see cref="string"/>, <see cref="DateOnly"/>, <see cref="PyDateTime"/>), or <c>null</c>.</summary>
    public object? Value { get; }

    /// <summary>Python <c>None</c>.</summary>
    public static GoldCell Null => default;

    /// <summary>An int.</summary>
    /// <param name="value">The value.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfInt(BigInteger value) => new(GoldKind.WholeNumber, value);

    /// <summary>A finite Decimal.</summary>
    /// <param name="value">The value.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfDecimal(PyDecimal value) => new(GoldKind.ExactDecimal, value);

    /// <summary>A NaN Decimal, kept as the text <c>str()</c> shows (<c>NaN</c>, <c>-NaN</c>, <c>NaN12</c>).</summary>
    /// <param name="text">The text.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfNaN(string text) => new(GoldKind.DecimalNaN, text);

    /// <summary>A str.</summary>
    /// <param name="value">The text.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfText(string value) => new(GoldKind.Text, value);

    /// <summary>A date.</summary>
    /// <param name="value">The date.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfDate(DateOnly value) => new(GoldKind.Date, value);

    /// <summary>A datetime.</summary>
    /// <param name="value">The datetime.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfDateTime(PyDateTime value) => new(GoldKind.DateTime, value);

    /// <summary>An optional string: <c>None</c> for null.</summary>
    /// <param name="value">The text or null.</param>
    /// <returns>The cell.</returns>
    public static GoldCell OfOptionalText(string? value) => value is null ? Null : OfText(value);

    /// <summary>The int held.</summary>
    public BigInteger AsInt => (BigInteger)Value!;

    /// <summary>The decimal held.</summary>
    public PyDecimal AsDecimal => (PyDecimal)Value!;

    /// <summary>The text held (for <see cref="GoldKind.Text"/> and <see cref="GoldKind.DecimalNaN"/>).</summary>
    public string AsText => (string)Value!;

    /// <summary>The date held.</summary>
    public DateOnly AsDate => (DateOnly)Value!;

    /// <summary>The datetime held.</summary>
    public PyDateTime AsDateTime => (PyDateTime)Value!;
}
