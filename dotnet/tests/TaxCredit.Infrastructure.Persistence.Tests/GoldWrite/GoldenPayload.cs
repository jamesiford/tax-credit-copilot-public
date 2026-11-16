using System.Globalization;
using System.IO.Compression;
using System.Numerics;
using System.Text.Json;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

internal static class GoldenPayload
{
    internal static IEnumerable<JsonElement> Records(string name)
    {
        using var file = File.OpenRead(Path.Combine(PersistenceFixture.Root, "parity", "goldens", name));
        using var gzip = new GZipStream(file, CompressionMode.Decompress);
        using var reader = new StreamReader(gzip);
        while (reader.ReadLine() is { } line)
        {
            using var document = JsonDocument.Parse(line);
            yield return document.RootElement.Clone();
        }
    }

    internal static JsonElement Scenario(string name) => Records("gold_payload.jsonl.gz")
        .First(r => r.GetProperty("k").GetString() == "run" && r.GetProperty("name").GetString() == name);

    internal static GoldRunPayload Read(JsonElement record)
    {
        var output = record.GetProperty("out");
        var tables = output.GetProperty("tables");
        IReadOnlyList<GoldRow> Rows(string name) => tables.GetProperty(name).GetProperty("rows").EnumerateArray()
            .Select(row => new GoldRow(name, GoldColumns.All[name], row.EnumerateArray().Select(Cell).ToArray())).ToArray();
        var manifest = output.GetProperty("manifest").EnumerateArray().Select(c => c[0].GetString() == "int"
            ? (object)c[1].GetInt64() : Cell(c).Value).ToArray();
        return new GoldRunPayload(output.GetProperty("client_id").GetInt64(), output.GetProperty("program_code").GetString()!,
            output.GetProperty("run_id").GetString()!, Cell(output.GetProperty("run_completed_at")).AsDateTime,
            output.GetProperty("manifest_columns").EnumerateArray().Select(c => c.GetString()!).ToArray(), manifest,
            Rows("employee_period_fact"), Rows("employee_eligibility"), Rows("onezero_matrix"), Rows("unit_month_summary"),
            Rows("run_method_summary"), Rows("unit_year_master"), Rows("unit_credit_installment"));
    }

    internal static GoldCell Cell(JsonElement cell) => cell[0].GetString() switch
    {
        "null" => GoldCell.Null,
        "int" => GoldCell.OfInt(BigInteger.Parse(cell[1].GetRawText(), CultureInfo.InvariantCulture)),
        "dec" => GoldCell.OfDecimal(PyDecimal.Parse(cell[1].GetString()!)),
        "str" => GoldCell.OfText(cell[1].GetString()!),
        "date" => GoldCell.OfDate(DateOnly.ParseExact(cell[1].GetString()!, "yyyy-MM-dd", CultureInfo.InvariantCulture)),
        "dt" => GoldCell.OfDateTime(PyDateTime.FromIsoFormat(cell[1].GetString()!)),
        var kind => throw new InvalidDataException("Unexpected projected cell kind: " + kind),
    };

    internal static GoldRunPayload Reidentify(GoldRunPayload payload, string runId, long? client = null, string? program = null)
    {
        var id = client ?? payload.ClientId;
        var code = program ?? payload.ProgramCode;
        IReadOnlyList<GoldRow> Rows(IReadOnlyList<GoldRow> rows) => rows.Select(row => new GoldRow(row.Table, row.Columns,
            row.Columns.Select((column, i) => column switch
            {
                "client_id" => GoldCell.OfInt(id),
                "run_id" => GoldCell.OfText(runId),
                "program_code" => GoldCell.OfText(code),
                _ => row.Cells[i],
            }).ToArray())).ToArray();
        var manifest = payload.ManifestRow.ToArray();
        manifest[0] = runId;
        manifest[1] = id;
        manifest[3] = code;
        return payload with
        {
            ClientId = id,
            ProgramCode = code,
            RunId = runId,
            ManifestRow = manifest,
            EmployeePeriodFact = Rows(payload.EmployeePeriodFact),
            EmployeeEligibility = Rows(payload.EmployeeEligibility),
            OneZeroMatrix = Rows(payload.OneZeroMatrix),
            UnitMonthSummary = Rows(payload.UnitMonthSummary),
            RunMethodSummary = Rows(payload.RunMethodSummary),
            UnitYearMaster = Rows(payload.UnitYearMaster),
            UnitCreditInstallment = Rows(payload.UnitCreditInstallment),
        };
    }

    internal static void Equal(GoldRunPayload expected, GoldRunPayload actual)
    {
        Assert.Equal(expected.ManifestColumns, actual.ManifestColumns);
        Assert.Equal(expected.ManifestRow, actual.ManifestRow);
        Assert.Equal(expected.RunCompletedAt, actual.RunCompletedAt);
        foreach (var ((name, expectedRows), (_, actualRows)) in expected.Tables.Zip(actual.Tables))
        {
            Assert.Equal(expectedRows.Count, actualRows.Count);
            for (var i = 0; i < expectedRows.Count; i++)
            {
                Assert.True(expectedRows[i].Cells.SequenceEqual(actualRows[i].Cells), name + " row " + i.ToString(CultureInfo.InvariantCulture));
            }
        }
    }
}
