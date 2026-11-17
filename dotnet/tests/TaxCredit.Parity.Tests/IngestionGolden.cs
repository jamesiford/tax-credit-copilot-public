using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Decoding shared by the ingestion-family golden replays (canonical mapping, grid filter, QC and triggers).</summary>
internal static class IngestionGolden
{
    /// <summary>A <c>{"$date": iso}</c> argument.</summary>
    public static DateOnly Date(object? v) => PyDate.FromIsoFormat((string)((PyDict)v!)["$date"]!);

    /// <summary>A list of row trees.</summary>
    public static List<PyDict> Rows(object? v) => ((List<object?>)v!).Cast<PyDict>().ToList();

    /// <summary>A number argument as Python's int-or-float, or <c>null</c> when the call omitted it.</summary>
    public static PyNumber? Number(PyDict a, string key) => !a.TryGetValue(key, out var v) ? null : v switch
    {
        long l => PyNumber.OfInt(l),
        double d => PyNumber.OfFloat(d),
        _ => throw new PyUnsupportedException("not a number: " + v?.GetType().Name),
    };

    /// <summary>An optional string argument (<c>null</c> when absent or <c>None</c>).</summary>
    public static string? Text(PyDict a, string key) => a.TryGetValue(key, out var v) ? (string?)v : null;

    /// <summary>The committed synthetic payroll CSV.</summary>
    public static string PayrollCsv => Path.Combine(Directory.GetParent(GoldenFiles.ParityDirectory)!.FullName, "backend", "data", "payroll_pay_periods.csv");

    /// <summary>The digest the exporters write for a big list: SHA-256 of its compact ASCII JSON.</summary>
    public static string Sha256(object? tree) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.ASCII.GetBytes(PyJson.Dumps(tree, sortKeys: false, compact: true, ensureAscii: true))));

    /// <summary>Decodes a <c>CanonicalRecord</c> dataclass tree.</summary>
    public static CanonicalRecord Record(object? tree)
    {
        var d = (PyDict)tree!;
        return new CanonicalRecord(
            (long)d["tax_year"]!, (string)d["employee_id"]!, (string)d["worksite_id"]!, (string)d["legal_entity_fein"]!, (string)d["pay_frequency"]!,
            Date(d["pay_period_start"]), Date(d["pay_period_end"]), Date(d["pay_date"]), (double)d["hours_worked"]!, (double)d["gross_wages"]!,
            (string)d["pay_code"]!, (string)d["job_title"]!, (string?)d["worksite_address"], (string?)d["unit_number"], (bool)d["includable"]!);
    }
}
