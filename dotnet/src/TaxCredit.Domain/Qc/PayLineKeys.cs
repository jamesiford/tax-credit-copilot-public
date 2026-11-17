using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Qc;

/// <summary>Python <c>tools/qc.py</c> <c>pay_line_keys</c>: one stable key per payroll LINE, so a QC resolution can name a line without an employee id.</summary>
public static class PayLineKeys
{
    // Everything that distinguishes one payroll LINE from another (Python `_LINE_FIELDS`): (employee, worksite, pay_date) is not a line.
    private static readonly string[] LineFields =
        ["Employee_ID", "Worksite_ID", "Tax_Year", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Pay_Code", "Hours_Worked", "Gross_Wages"];

    /// <summary>Python <c>pay_line_keys(rows)</c>: <c>sha256(content)[:20] + "." + occurrence</c> for each row, aligned with <paramref name="rows"/>.</summary>
    /// <remarks>
    /// Why the occurrence suffix: the source does hold exact duplicate lines. Identical lines are interchangeable, so which copy is "first" does
    /// not matter and the key survives a change in read order. It is a hash so an employee id never reaches the resolve URL.
    /// </remarks>
    /// <param name="rows">The payroll rows.</param>
    /// <returns>The keys.</returns>
    public static List<string> Keys(IEnumerable<PyDict> rows)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var seen = new Dictionary<string, int>(StringComparer.Ordinal);
        var keys = new List<string>();
        foreach (var row in rows)
        {
            var digest = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(LineContent(row))))[..20];
            seen[digest] = seen.GetValueOrDefault(digest) + 1;
            keys.Add(digest + "." + seen[digest].ToString(System.Globalization.CultureInfo.InvariantCulture));
        }

        return keys;
    }

    /// <summary>Python <c>_line_content</c>: the pipe-joined content of the nine line fields.</summary>
    /// <param name="row">The row.</param>
    /// <returns>The text that is hashed.</returns>
    public static string LineContent(PyDict row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var parts = new List<string>(LineFields.Length);
        foreach (var field in LineFields)
        {
            row.TryGetValue(field, out var value);
            var truthy = ProximityCoerce.Truthy(value);
            parts.Add(field switch
            {
                "Hours_Worked" or "Gross_Wages" => PyFormat.Fixed(truthy ? ProximityCoerce.ToFloat(value) : 0.0, 4),
                "Pay_Period_Start" or "Pay_Period_End" or "Pay_Date" => PyStr.Prefix(truthy ? ProximityCoerce.Str(value) : string.Empty, 10),
                _ => truthy ? ProximityCoerce.Str(value) : string.Empty,
            });
        }

        return string.Join('|', parts);
    }
}
