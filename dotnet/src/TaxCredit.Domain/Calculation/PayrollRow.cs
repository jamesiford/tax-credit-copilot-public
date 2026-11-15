using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>What a payroll cell held in the loosely typed Python row: absent key, <c>None</c>, str, int or float.</summary>
public enum CellKind
{
    /// <summary>The key is not in the row (<c>row["x"]</c> raises <c>KeyError</c>, <c>row.get("x")</c> gives the default).</summary>
    Absent,

    /// <summary>Python <c>None</c>.</summary>
    Null,

    /// <summary>A string.</summary>
    Text,

    /// <summary>An int.</summary>
    WholeNumber,

    /// <summary>A float.</summary>
    Real,
}

/// <summary>One cell of a payroll row, preserving the Python type so coercions can be mirrored exactly.</summary>
/// <param name="Kind">The kind of value held.</param>
/// <param name="Text">The string when <see cref="CellKind.Text"/>.</param>
/// <param name="IntValue">The int when <see cref="CellKind.WholeNumber"/>.</param>
/// <param name="FloatValue">The float when <see cref="CellKind.Real"/>.</param>
public readonly record struct RowCell(CellKind Kind, string? Text = null, long IntValue = 0, double FloatValue = 0)
{
    /// <summary>The key is absent.</summary>
    public static RowCell Absent { get; } = new(CellKind.Absent);

    /// <summary>Python <c>None</c>.</summary>
    public static RowCell Null { get; } = new(CellKind.Null);

    /// <summary>True unless the key is absent.</summary>
    public bool IsPresent => Kind != CellKind.Absent;

    /// <summary>A string cell.</summary>
    /// <param name="text">The text.</param>
    /// <returns>The cell.</returns>
    public static RowCell OfText(string text) => new(CellKind.Text, text);

    /// <summary>An int cell.</summary>
    /// <param name="value">The value.</param>
    /// <returns>The cell.</returns>
    public static RowCell OfInt(long value) => new(CellKind.WholeNumber, null, value);

    /// <summary>A float cell.</summary>
    /// <param name="value">The value.</param>
    /// <returns>The cell.</returns>
    public static RowCell OfFloat(double value) => new(CellKind.Real, null, 0, value);
}

/// <summary>
/// A payroll row in the Silver Record Layout, reduced to the columns the engine's outputs use. Python passes loosely
/// typed dicts; this keeps each cell's Python type (<see cref="RowCell"/>) and mirrors the access rules:
/// <c>r["x"]</c> is <see cref="Require"/> (KeyError when absent), <c>r.get("x", d)</c> is Python <c>get</c> with a default.
/// </summary>
/// <param name="EmployeeId">Employee_ID.</param>
/// <param name="WorksiteId">Worksite_ID.</param>
/// <param name="EntityFein">Entity_FEIN.</param>
/// <param name="PayPeriodStart">Pay_Period_Start (raw text, never normalised).</param>
/// <param name="PayPeriodEnd">Pay_Period_End (raw text).</param>
/// <param name="PayDate">Pay_Date (raw text).</param>
/// <param name="HoursWorked">Hours_Worked.</param>
/// <param name="GrossWages">Gross_Wages.</param>
/// <param name="PayCode">Pay_Code.</param>
/// <param name="WorkState">Work_State.</param>
public sealed record PayrollRow(
    RowCell EmployeeId,
    RowCell WorksiteId,
    RowCell EntityFein,
    RowCell PayPeriodStart,
    RowCell PayPeriodEnd,
    RowCell PayDate,
    RowCell HoursWorked,
    RowCell GrossWages,
    RowCell PayCode,
    RowCell WorkState)
{
    /// <summary>Python <c>row["Employee_ID"]</c> for a column the port models as text-or-None.</summary>
    /// <param name="cell">The cell.</param>
    /// <param name="column">The column name for the KeyError.</param>
    /// <returns>The text, or null for None.</returns>
    /// <exception cref="PyKeyError">When the key is absent.</exception>
    /// <exception cref="PyUnsupportedException">When the cell is a number (not modelled for identifier and date columns).</exception>
    public static string? Require(RowCell cell, string column)
    {
        switch (cell.Kind)
        {
            case CellKind.Absent:
                throw new PyKeyError(column);
            case CellKind.Null:
                return null;
            case CellKind.Text:
                return cell.Text;
            default:
                throw new PyUnsupportedException($"Numeric {column} cells are not modelled");
        }
    }

    /// <summary>Python <c>row["Employee_ID"]</c>.</summary>
    /// <returns>The id or null.</returns>
    public string? RequireEmployeeId() => Require(EmployeeId, "Employee_ID");

    /// <summary>Python <c>row["Worksite_ID"]</c>.</summary>
    /// <returns>The id or null.</returns>
    public string? RequireWorksiteId() => Require(WorksiteId, "Worksite_ID");

    /// <summary>Python <c>row["Pay_Period_Start"]</c>.</summary>
    /// <returns>The raw text or null.</returns>
    public string? RequireStart() => Require(PayPeriodStart, "Pay_Period_Start");

    /// <summary>Python <c>row["Pay_Period_End"]</c>.</summary>
    /// <returns>The raw text or null.</returns>
    public string? RequireEnd() => Require(PayPeriodEnd, "Pay_Period_End");

    /// <summary>Python <c>row["Pay_Date"]</c>.</summary>
    /// <returns>The raw text or null.</returns>
    public string? RequirePayDate() => Require(PayDate, "Pay_Date");

    /// <summary>Python <c>row["Hours_Worked"]</c>: the cell, KeyError when absent.</summary>
    /// <returns>The cell.</returns>
    public RowCell RequireHours() => HoursWorked.IsPresent ? HoursWorked : throw new PyKeyError("Hours_Worked");

    /// <summary>Python <c>row["Gross_Wages"]</c>: the cell, KeyError when absent.</summary>
    /// <returns>The cell.</returns>
    public RowCell RequireWages() => GrossWages.IsPresent ? GrossWages : throw new PyKeyError("Gross_Wages");

    /// <summary>Python <c>row.get("Entity_FEIN", "")</c>.</summary>
    /// <returns>The FEIN text, null when the cell is None.</returns>
    public string? EntityFeinOrEmpty() => EntityFein.IsPresent ? Require(EntityFein, "Entity_FEIN") : string.Empty;

    /// <summary>Python <c>str(row.get("Pay_Code", "Regular"))</c> (so None becomes <c>"None"</c>).</summary>
    /// <returns>The pay code text.</returns>
    public string PayCodeText() => PayCode.Kind switch
    {
        CellKind.Absent => "Regular",
        CellKind.Null => "None",
        CellKind.Text => PayCode.Text!,
        _ => throw new PyUnsupportedException("Numeric Pay_Code cells are not modelled"),
    };

    /// <summary>A copy with Hours_Worked and Gross_Wages replaced (Python <c>dict(r)</c> then assignment).</summary>
    /// <param name="hours">New hours cell.</param>
    /// <param name="wages">New wages cell.</param>
    /// <returns>The copy.</returns>
    public PayrollRow WithAmounts(RowCell hours, RowCell wages) => this with { HoursWorked = hours, GrossWages = wages };
}

/// <summary>Python <c>_coerce_float</c> and <c>_parse_iso</c>, the two coercions every engine step relies on.</summary>
public static class Coerce
{
    /// <summary>
    /// <c>_coerce_float(v)</c>: <c>None</c> and <c>""</c> are 0.0, anything else goes through <c>float()</c>.
    /// </summary>
    /// <param name="cell">The cell (must be present).</param>
    /// <returns>The value.</returns>
    /// <exception cref="PyValueError">When a string is not a float literal.</exception>
    public static double ToFloat(RowCell cell)
    {
        switch (cell.Kind)
        {
            case CellKind.Null:
                return 0.0;
            case CellKind.Text:
                if (cell.Text!.Length == 0)
                {
                    return 0.0;
                }

                return PyFloat.TryParse(cell.Text, out var v) ? v : throw new PyValueError($"could not convert string to float: '{cell.Text}'");
            case CellKind.WholeNumber:
                return cell.IntValue;
            case CellKind.Real:
                return cell.FloatValue;
            default:
                throw new PyKeyError("cell");
        }
    }

    /// <summary><c>_parse_iso(s)</c> for a text-or-None cell: <c>date.fromisoformat(str(s)[:10])</c>.</summary>
    /// <param name="text">The raw text; null is Python <c>None</c>, whose <c>str()</c> is <c>"None"</c>.</param>
    /// <returns>The date.</returns>
    /// <exception cref="PyValueError">When the first 10 characters are not an ISO date.</exception>
    public static DateOnly ParseIso(string? text) => PyDate.FromIsoFormat(PyStr.Prefix(text ?? "None", 10));
}
