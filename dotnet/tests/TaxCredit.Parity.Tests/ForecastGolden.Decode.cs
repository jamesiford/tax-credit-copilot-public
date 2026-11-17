using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Forecast;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Simulation;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>Decoding of golden arguments (tagged dates, payroll selections, packs, rows) and encoding of result rows.</summary>
internal sealed partial class ForecastGolden
{
    // ------------------------------------------------------------------------------------------ decoding

    private static double? Opt(object? v) => v switch
    {
        null => null,
        long l => l,
        double d => d,
        _ => throw new PyUnsupportedException("not a number: " + v.GetType().Name),
    };

    private static PyNumber Num(object? v) => v is long l ? PyNumber.OfInt(l) : PyNumber.OfFloat((double)v!);

    private static DateOnly Date(object? v) => PyDate.FromIsoFormat((string)((PyDict)v!)["$date"]!);

    private static List<IReadOnlyList<PyNumber>> Summary(object? v) =>
        ((List<object?>)v!).Select(u => (IReadOnlyList<PyNumber>)((List<object?>)((PyDict)u!)["month_totals"]!).Select(Num).ToList()).ToList();

    private List<PayrollRow> Resolved(object? v)
    {
        if (v is PyDict { Count: 1 } d && d.TryGetValue("$payroll", out var sel))
        {
            return Select((PyDict)sel!);
        }

        return Rows((List<object?>)v!);
    }

    private List<PayrollRow> Select(PyDict sel)
    {
        var prefix = sel.TryGetValue("prefix", out var p) ? (string?)p : null;
        var fy = sel.TryGetValue("fy", out var f) ? (long?)f : null;
        var fyEnd = sel.TryGetValue("fy_end", out var fe) ? (long)fe! : 12L;
        var rows = _payroll.Value.Where(r => (prefix is null || r.RequireWorksiteId()!.StartsWith(prefix, StringComparison.Ordinal))
            && (fy is null || OneZeroCalendar.FiscalYearOf(Coerce.ParseIso(r.RequirePayDate()), fyEnd) == fy)).ToList();
        if (sel.TryGetValue("max_employees", out var max) && max is long n)
        {
            var keep = rows.Select(r => r.RequireEmployeeId()).Distinct().Take((int)n).ToHashSet();
            rows = rows.Where(r => keep.Contains(r.RequireEmployeeId())).ToList();
        }

        return rows;
    }

    private OneZeroPack Pack(object? v)
    {
        var d = (PyDict)v!;
        if (d.TryGetValue("$pack", out var spec))
        {
            var s = (PyDict)spec!;
            return _library.LoadPackOneZero((string)s["key"]!, (long)s["tax_year"]!) ?? throw new PyUnsupportedException("no pack");
        }

        var p = (PyDict)d["$pack_spec"]!;
        var band = p.TryGetValue("pt_band_hours", out var b) && b is List<object?> bl ? (Num(bl[0]), Num(bl[1])) : ((PyNumber, PyNumber)?)null;
        return new OneZeroPack
        {
            MinWeeklyHours = Num(p["min_weekly_hours"]),
            MinWeeklyWages = Num(p["min_weekly_wages"]),
            Citation = p.TryGetValue("citation", out var c) ? (string)c! : string.Empty,
            PtBandHours = band,
            PtWeight = p.TryGetValue("pt_weight", out var w) ? Num(w) : null,
            IncludedPayCodes = p.TryGetValue("included_pay_codes", out var ic) ? ((List<object?>)ic!).Cast<string>().ToArray() : null,
        };
    }

    private static List<PayrollRow> Rows(object? tree) => ((List<object?>)tree!).Select(r => ToRow((PyDict)r!)).ToList();

    private static List<PayrollRow> Rows(PyDict payrollCall) => Rows(((PyDict)payrollCall["out"]!)["result"]);

    private static PyDict Payroll() => Calls().First(c => (string)c["fn"]! == "_payroll");

    private static RowCell Cell(PyDict d, string key) => !d.TryGetValue(key, out var v) ? RowCell.Absent : v switch
    {
        null => RowCell.Null,
        string s => RowCell.OfText(s),
        long l => RowCell.OfInt(l),
        double x => RowCell.OfFloat(x),
        _ => throw new PyUnsupportedException("unsupported cell " + v.GetType().Name),
    };

    private static PayrollRow ToRow(PyDict o) => new(
        Cell(o, "Employee_ID"), Cell(o, "Worksite_ID"), Cell(o, "Entity_FEIN"), Cell(o, "Pay_Period_Start"), Cell(o, "Pay_Period_End"),
        Cell(o, "Pay_Date"), Cell(o, "Hours_Worked"), Cell(o, "Gross_Wages"), Cell(o, "Pay_Code"), Cell(o, "Work_State"), Cell(o, "Job_Title"));

    private static object? CellValue(RowCell c) => c.Kind switch
    {
        CellKind.Text => c.Text,
        CellKind.WholeNumber => c.IntValue,
        CellKind.Real => c.FloatValue,
        _ => null,
    };

    private static List<object?> RowsTree(IReadOnlyList<PayrollRow> rows) => rows.Select(r => (object?)RowTree(r)).ToList();

    private static PyDict RowTree(PayrollRow r)
    {
        var cells = new[] { r.EmployeeId, r.WorksiteId, r.EntityFein, r.PayPeriodStart, r.PayPeriodEnd, r.PayDate, r.HoursWorked, r.GrossWages, r.PayCode, r.WorkState, r.JobTitle };
        var d = new PyDict();
        for (var i = 0; i < Columns.Length; i++)
        {
            if (cells[i].IsPresent)
            {
                d.Add(Columns[i], CellValue(cells[i]));
            }
        }

        return d;
    }
}
