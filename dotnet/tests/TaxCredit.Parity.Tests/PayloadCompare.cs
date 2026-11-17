using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Bit-exact comparison of C# values against the exporter's typed cells (<c>["dec","1.00"]</c>, <c>["int",5]</c>, <c>["float",repr,bits]</c> ...).</summary>
internal static class PayloadCompare
{
    /// <summary>The first difference between a recorded typed cell and a Gold cell, or <c>null</c>.</summary>
    public static string? Cell(JsonElement expected, GoldCell actual)
    {
        var kind = expected[0].GetString();
        return (kind, actual.Kind) switch
        {
            ("null", GoldKind.Null) => null,
            ("int", GoldKind.WholeNumber) when expected[1].GetRawText() == actual.AsInt.ToString(CultureInfo.InvariantCulture) => null,
            ("dec", GoldKind.ExactDecimal) when expected[1].GetString() == actual.AsDecimal.ToString() => null,
            ("nan", GoldKind.DecimalNaN) when expected[1].GetString() == actual.AsText => null,
            ("str", GoldKind.Text) when string.Equals(expected[1].GetString(), actual.AsText, StringComparison.Ordinal) => null,
            ("date", GoldKind.Date) when expected[1].GetString() == actual.AsDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) => null,
            ("dt", GoldKind.DateTime) when expected[1].GetString() == actual.AsDateTime.IsoFormat() => null,
            _ => $"expected {expected.GetRawText()}, got {actual.Kind} {Show(actual)}",
        };
    }

    /// <summary>The typed cell of a manifest value (<c>string</c>, <c>long</c>, date, datetime or <c>null</c>).</summary>
    public static GoldCell OfValue(object? v) => v switch
    {
        null => GoldCell.Null,
        string s => GoldCell.OfText(s),
        long l => GoldCell.OfInt(l),
        DateOnly d => GoldCell.OfDate(d),
        PyDateTime t => GoldCell.OfDateTime(t),
        _ => throw new InvalidOperationException("unexpected manifest value " + v.GetType().Name),
    };

    /// <summary>Compares one table: its columns, its row count, every cell of every row, then the ordered digest of the cells' JSON.</summary>
    public static string? Table(string name, JsonElement expected, IReadOnlyList<GoldRow> rows)
    {
        var columns = expected.GetProperty("columns").EnumerateArray().Select(c => c.GetString()).ToList();
        if (!columns.SequenceEqual(GoldColumns.All[name]))
        {
            return $"{name}: column list differs";
        }

        var n = expected.GetProperty("n").GetInt32();
        var rowsJson = expected.GetProperty("rows");
        if (n != rows.Count || rowsJson.GetArrayLength() != n)
        {
            return $"{name}: {rows.Count} rows, Python {n}";
        }

        var i = 0;
        foreach (var row in rowsJson.EnumerateArray())
        {
            var j = 0;
            foreach (var cell in row.EnumerateArray())
            {
                if (Cell(cell, rows[i].Cells[j]) is { } diff)
                {
                    return $"{name} row {i} column {columns[j]}: {diff}";
                }

                j++;
            }

            i++;
        }

        return Digest(rows) == expected.GetProperty("digest").GetString() ? null : $"{name}: the ordered digest differs";
    }

    /// <summary>SHA-256 over each row's compact JSON followed by a newline (the exporter's <c>table_record</c>).</summary>
    public static string Digest(IReadOnlyList<GoldRow> rows)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var row in rows)
        {
            var cells = row.Cells.Select(c => (object?)GoldReplay.Cell(c)).ToList();
            hash.AppendData(Encoding.ASCII.GetBytes(PyJson.Dumps(cells, sortKeys: false, compact: true) + "\n"));
        }

        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    /// <summary>A claim as the exporter records it: its fields in dataclass order without <c>claim_id</c>, <c>decided_at</c> and <c>effective_*</c>, each a typed cell.</summary>
    public static string? Claim(JsonElement expected, ProgramClaim claim)
    {
        var floatBits = (double? v) => v is { } d ? new object?[] { "float", PyFloat.Repr(d), ((ulong)BitConverter.DoubleToInt64Bits(d)).ToString("x16", CultureInfo.InvariantCulture) } : ["null"];
        var fields = new (string Name, object?[] Cell)[]
        {
            ("client_id", ["int", claim.ClientId]), ("program_code", ["str", claim.ProgramCode]), ("tax_year", ["int", claim.TaxYear]),
            ("status", ["str", claim.Status.Value()]), ("provenance", ["str", claim.Provenance.Value()]), ("identified_usd", ["dec", claim.IdentifiedUsd.ToString()]),
            ("claimed_usd", ["dec", claim.ClaimedUsd.ToString()]), ("certified_usd", ["dec", claim.CertifiedUsd.ToString()]),
            ("average_headcount", floatBits(claim.AverageHeadcount)), ("base_average_headcount", floatBits(claim.BaseAverageHeadcount)), ("threshold_jobs", floatBits(claim.ThresholdJobs)),
            ("is_base_year", ["bool", claim.IsBaseYear]), ("entity_id", claim.EntityId is { } e ? ["int", e] : ["null"]), ("identified_run_id", Text(claim.IdentifiedRunId)),
            ("assumption_set_id", Text(claim.AssumptionSetId)), ("rule_pack_version", Text(claim.RulePackVersion)),
            ("filed_on", claim.FiledOn is { } f ? ["date", f.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)] : ["null"]),
            ("filing_reference", Text(claim.FilingReference)), ("decided_by", Text(claim.DecidedBy)), ("decline_reason", Text(claim.DeclineReason)),
        };
        var recorded = expected.EnumerateArray().ToList();
        if (recorded.Count != fields.Length)
        {
            return $"claim has {recorded.Count} fields, C# {fields.Length}";
        }

        for (var i = 0; i < fields.Length; i++)
        {
            var want = recorded[i];
            var got = PyJson.Dumps(fields[i].Cell.ToList(), sortKeys: false, compact: true);
            if (want[0].GetString() != fields[i].Name || want[1].GetRawText() != got)
            {
                return $"claim field {fields[i].Name}: expected {want[1].GetRawText()}, got {got}";
            }
        }

        return null;
    }

    private static object?[] Text(string? s) => s is null ? ["null"] : ["str", s];

    private static string Show(GoldCell c) => c.Kind == GoldKind.Null ? "null" : c.Value?.ToString() ?? "?";
}
