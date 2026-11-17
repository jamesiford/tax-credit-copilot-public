using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>Run identity: <c>calculation_id</c> of <c>tools/gold_projection.py</c>.</summary>
public static partial class GoldProjection
{
    private static readonly string[] PayrollFields =
    [
        "Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code",
    ];

    /// <summary>
    /// Python <c>calculation_id</c>: a deterministic SHA-256 fingerprint of everything that decides the answer. Two runs over the same payroll, statute
    /// and assumptions give the same id; a run over corrected payroll does not.
    /// </summary>
    /// <remarks>
    /// The payroll contributes a digest of nine identifying and monetary fields, each as <c>str(value or "")</c> (so <c>0</c>, <c>0.0</c>, <c>""</c> and
    /// <c>None</c> are all the empty text, a NaN is the text <c>nan</c>), NUL-joined, UTF-8 encoded (a lone surrogate raises) and newline-terminated. The
    /// seed then joins the identity, the window dates' <c>isoformat()</c>, three floors rendered with <c>str()</c> (<c>None</c> when absent) and the
    /// assumption ids; a non-string id is a <c>TypeError</c> from <c>str.join</c> naming its position in the list.
    /// </remarks>
    /// <param name="clientId">The client (anything <c>str()</c> renders; an int in production).</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="taxYear">The tax year (anything <c>str()</c> renders; an int in production).</param>
    /// <param name="windowBegin">The fiscal window start (a date or datetime).</param>
    /// <param name="windowEnd">The fiscal window end (a date or datetime).</param>
    /// <param name="floors">The statutory floors mapping.</param>
    /// <param name="assumptionIds">The assumption set ids.</param>
    /// <param name="rows">The payroll rows.</param>
    /// <returns>64 lowercase hex digits.</returns>
    /// <exception cref="PyAttributeError">When a window bound has no <c>isoformat</c>.</exception>
    /// <exception cref="PyTypeError">When an assumption id is not text.</exception>
    /// <exception cref="PyUnicodeEncodeError">When any text holds a lone surrogate.</exception>
    public static string CalculationId(
        object? clientId,
        string programCode,
        object? taxYear,
        object? windowBegin,
        object? windowEnd,
        PyDict floors,
        IReadOnlyList<object?> assumptionIds,
        IEnumerable<PyDict> rows)
    {
        ArgumentNullException.ThrowIfNull(programCode);
        ArgumentNullException.ThrowIfNull(floors);
        ArgumentNullException.ThrowIfNull(assumptionIds);
        ArgumentNullException.ThrowIfNull(rows);
        var digest = PayrollDigest(rows);
        List<object?> parts =
        [
            GoldValues.Str(clientId), programCode, GoldValues.Str(taxYear), IsoFormat(windowBegin), IsoFormat(windowEnd),
            GoldValues.Str(Get(floors, "minimum_average_weekly_hours")), GoldValues.Str(Get(floors, "minimum_average_weekly_wages_usd")),
            GoldValues.Str(Get(floors, "source")), .. assumptionIds, digest,
        ];
        var seed = new StringBuilder();
        for (var i = 0; i < parts.Count; i++)
        {
            seed.Append(i == 0 ? string.Empty : "\0").Append(parts[i] as string
                ?? throw new PyTypeError($"sequence item {i.ToString(CultureInfo.InvariantCulture)}: expected str instance, {GoldValues.TypeName(parts[i])} found"));
        }

        return Convert.ToHexString(SHA256.HashData(PyUtf8.Encode(seed.ToString()))).ToLowerInvariant();
    }

    private static string PayrollDigest(IEnumerable<PyDict> rows)
    {
        using var payroll = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var row in rows)
        {
            payroll.AppendData(PyUtf8.Encode(string.Join("\0", PayrollFields.Select(field => OrEmpty(Get(row, field))))));
            payroll.AppendData("\n"u8);
        }

        return Convert.ToHexString(payroll.GetHashAndReset()).ToLowerInvariant();
    }
}
