using System.Text.Json;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate CAP (engine to Gold payload): replays every run of <c>gold_payload.jsonl.gz</c>, the production <c>handle_run_client_calculation</c> on CPython 3.12
/// with a capturing writer, against <see cref="ClientCalculation"/>. Every row of all seven <c>tcc_gold</c> tables, every manifest column, the handler's result
/// and the claims the assessment records are compared cell by cell; a run that raised must raise the same type with the same message.
/// </summary>
public sealed class ClientCalculationParityTests
{
    [Fact]
    public void Every_run_matches_python_bit_for_bit()
    {
        var failures = new List<string>();
        var compared = new Dictionary<string, (int Rows, int Runs)>();
        var runs = 0;
        var errors = 0;
        foreach (var line in PayloadGolden.Lines(PayloadGolden.Main, "run"))
        {
            using var doc = JsonDocument.Parse(line);
            var record = doc.RootElement;
            runs++;
            errors += record.TryGetProperty("err", out _) ? 1 : 0;
            foreach (var diff in Replay(record, compared))
            {
                failures.Add($"{record.GetProperty("name").GetString()}: {diff}");
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count} runs diverged from Python:\n" + string.Join("\n", failures.Take(12)));
        Assert.True(runs >= 19 && errors >= 6, $"corpus too thin: {runs} runs, {errors} raised");
        foreach (var table in compared)
        {
            Assert.True(table.Value.Rows > 100, $"{table.Key} is barely covered ({table.Value.Rows} rows)");
        }
    }

    /// <summary>Replays one run; returns every difference found (empty when identical). Adds the rows compared per table to <paramref name="compared"/>.</summary>
    internal static List<string> Replay(JsonElement record, Dictionary<string, (int Rows, int Runs)>? compared = null)
    {
        var diffs = new List<string>();
        var world = PayloadWorld.Instance;
        var name = record.GetProperty("name").GetString()!;
        var source = world.SourceOf(record.GetProperty("source"));
        var (pipeline, writer, claims, defaults) = world.Pipeline(name, source, SavedYears(record), SeedClaims(record));
        PyDict? result = null;
        Exception? raised = null;
        try
        {
            result = pipeline.Run(Command(record.GetProperty("args")).Validated(defaults));
        }
        catch (Exception e)
        {
            // Any exception is a divergence report, not a crash: a port bug must read as "diverged", like a wrong cell.
            raised = e;
        }

        if (record.TryGetProperty("err", out var err))
        {
            var type = raised is PyException py ? py.PythonType : raised?.GetType().Name;
            if (raised is null || type != err.GetString() || raised.Message != record.GetProperty("msg").GetString())
            {
                diffs.Add($"expected {err.GetString()}: {record.GetProperty("msg").GetString()}; got {type}: {raised?.Message ?? "a result"}");
            }

            return diffs;
        }

        if (raised is not null)
        {
            return [$"C# raised {(raised is PyException p ? p.PythonType : raised.GetType().Name)}: {raised.Message}"];
        }

        Compare(record.GetProperty("out"), result!, writer.Payload!, claims, diffs, compared);
        return diffs;
    }

    private static void Compare(JsonElement expected, PyDict result, GoldRunPayload payload, CapturingClaims claims, List<string> diffs, Dictionary<string, (int, int)>? compared)
    {
        var want = (PyDict)PyJson.Loads(expected.GetProperty("result").GetRawText())!;
        if (ClaimGolden.Compare(want, result, "result") is { } resultDiff)
        {
            diffs.Add(resultDiff);
        }

        if (payload.RunId != expected.GetProperty("run_id").GetString() || payload.ClientId != expected.GetProperty("client_id").GetInt64() || payload.ProgramCode != expected.GetProperty("program_code").GetString())
        {
            diffs.Add("payload identity differs");
        }

        if (PayloadCompare.Cell(expected.GetProperty("run_completed_at"), GoldCell.OfDateTime(payload.RunCompletedAt)) is { } completed)
        {
            diffs.Add("run_completed_at: " + completed);
        }

        var columns = expected.GetProperty("manifest_columns").EnumerateArray().Select(c => c.GetString()).ToList();
        if (!columns.SequenceEqual(payload.ManifestColumns))
        {
            diffs.Add("manifest columns differ");
        }

        var manifest = expected.GetProperty("manifest").EnumerateArray().ToList();
        for (var i = 0; i < manifest.Count && i < payload.ManifestRow.Count; i++)
        {
            if (PayloadCompare.Cell(manifest[i], PayloadCompare.OfValue(payload.ManifestRow[i])) is { } diff)
            {
                diffs.Add($"manifest {columns[i]}: {diff}");
            }
        }

        foreach (var (table, rows) in payload.Tables)
        {
            if (PayloadCompare.Table(table, expected.GetProperty("tables").GetProperty(table), rows) is { } diff)
            {
                diffs.Add(diff);
            }

            if (compared is not null)
            {
                var (n, r) = compared.GetValueOrDefault(table);
                compared[table] = (n + rows.Count, r + 1);
            }
        }

        var recorded = expected.GetProperty("claims").EnumerateArray().ToList();
        if (recorded.Count != claims.Recorded.Count)
        {
            diffs.Add($"{claims.Recorded.Count} claims recorded, Python {recorded.Count}");
            return;
        }

        for (var i = 0; i < recorded.Count; i++)
        {
            if (PayloadCompare.Claim(recorded[i], claims.Recorded[i]) is { } diff)
            {
                diffs.Add($"claim {i}: {diff}");
            }
        }
    }

    private static RunClientCalculationCommand Command(JsonElement args) => new(
        args.GetProperty("client_id").GetInt64(),
        args.GetProperty("tax_year").GetInt64(),
        args.TryGetProperty("state", out var s) ? s.GetString() : null,
        args.TryGetProperty("program_code", out var p) ? p.GetString() : null,
        args.TryGetProperty("assess_tax_years", out var a) ? a.EnumerateArray().Select(y => y.GetInt64()).ToList() : null,
        args.TryGetProperty("actor", out var actor) ? actor.GetString()! : "system");

    private static Dictionary<(long, string), IReadOnlyDictionary<string, long>> SavedYears(JsonElement record) =>
        record.GetProperty("overrides").EnumerateArray().ToDictionary(
            o => (o[0].GetInt64(), o[1].GetString()!),
            o => (IReadOnlyDictionary<string, long>)o[2].EnumerateArray().ToDictionary(u => u[0].GetString()!, u => u[1].GetInt64()));

    private static List<ProgramClaim> SeedClaims(JsonElement record) =>
        record.GetProperty("seed_claims").EnumerateArray().Select(c => ProgramClaim.Create(new ClaimSpec
        {
            ClientId = c[0].GetInt64(),
            ProgramCode = c[1].GetString(),
            TaxYear = c[2].GetInt64(),
            Status = ClaimEnumExtensions.StatusFromValue(c[3].GetString()!),
            Provenance = Provenance.Computed,
            IdentifiedUsd = PyDecimal.Parse(c[4].GetString()!),
            DecidedBy = "analyst",
            DeclineReason = c[3].GetString() == "declined" ? "prefers R&D" : null,
        })).ToList();
}
