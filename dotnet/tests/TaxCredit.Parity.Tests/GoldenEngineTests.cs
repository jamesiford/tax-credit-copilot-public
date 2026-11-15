using System.IO.Compression;
using System.Text.Json;
using TaxCredit.Domain.Calculation;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate G2: every golden produced by the Python production engine (<c>parity/goldens/engine.jsonl.gz</c>) must match the
/// C# port bit for bit: result tree (types, key order, double bits), calculation trail including its SHA-256
/// evidence hash, the independent float-bit digest, and the Python exception type for scenarios that raise.
/// </summary>
public sealed class GoldenEngineTests
{
    private static readonly Lazy<Dictionary<string, List<PayrollRow>>> Datasets = new(LoadDatasets);

    private static Dictionary<string, List<PayrollRow>> LoadDatasets()
    {
        var result = new Dictionary<string, List<PayrollRow>>(StringComparer.Ordinal);
        foreach (var line in Lines("datasets.jsonl.gz"))
        {
            using var doc = JsonDocument.Parse(line);
            if (doc.RootElement.TryGetProperty("name", out var name))
            {
                result[name.GetString()!] = EngineRunner.Rows(doc.RootElement.GetProperty("rows"));
            }
        }

        return result;
    }

    internal static IEnumerable<string> Lines(string file)
    {
        using var stream = File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", file));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            yield return line;
        }
    }

    /// <summary>Compares one scenario; returns null when it matches.</summary>
    internal static string? Check(JsonElement scenario, List<PayrollRow>? dataset)
    {
        var expected = scenario.GetProperty("expected");
        var outcome = EngineRunner.Execute(scenario, dataset);
        var id = scenario.GetProperty("id").GetString();
        if (!expected.GetProperty("ok").GetBoolean())
        {
            var err = expected.GetProperty("error").GetString();
            return !outcome.Ok && outcome.Error == err ? null : $"{id}: expected {err}, got {(outcome.Ok ? "a result" : outcome.Error)}";
        }

        if (!outcome.Ok)
        {
            return $"{id}: expected a result, got {outcome.Error}";
        }

        var diff = JsonTree.Diff(JsonTree.Read(expected.GetProperty("result")), outcome.Result, "result");
        if (diff is not null)
        {
            return $"{id}: {diff}";
        }

        var trailElement = expected.GetProperty("trail");
        diff = JsonTree.Diff(trailElement.ValueKind == JsonValueKind.Null ? null : JsonTree.Read(trailElement), outcome.Trail, "trail");
        if (diff is not null)
        {
            return $"{id}: {diff}";
        }

        var digest = expected.GetProperty("float_digest").GetString();
        return outcome.FloatDigest == digest ? null : $"{id}: float digest {outcome.FloatDigest} expected {digest}";
    }

    [Theory]
    [InlineData("pay_period")]
    [InlineData("min_max")]
    [InlineData("preprocess")]
    [InlineData("first_measurable_month")]
    [InlineData("unreachable_months")]
    [InlineData("apply_pay_code_policy")]
    [InlineData("average_headcount")]
    [InlineData("rows_for_state_year")]
    [InlineData("row_states")]
    [InlineData("states_present")]
    [InlineData("helper")]
    [InlineData("fiscal")]
    [InlineData("floors")]
    public void Engine_goldens_match_the_python_oracle_bit_for_bit(string op)
    {
        var count = 0;
        var failed = 0;
        var messages = new List<string>();
        foreach (var line in Lines("engine.jsonl.gz"))
        {
            if (!line.Contains("\"op\":\"" + op + "\"", StringComparison.Ordinal) || line.StartsWith("{\"k\":\"meta\"", StringComparison.Ordinal))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var s = doc.RootElement;
            if (s.GetProperty("op").GetString() != op)
            {
                continue;
            }

            count++;
            List<PayrollRow>? dataset = s.TryGetProperty("dataset", out var ds) ? Datasets.Value[ds.GetString()!] : null;
            var error = Check(s, dataset);
            if (error is not null)
            {
                failed++;
                if (messages.Count < 6)
                {
                    messages.Add(error.Length > 400 ? error[..400] : error);
                }
            }
        }

        Assert.True(count > 0, "no scenarios for " + op);
        Assert.True(failed == 0, $"{failed}/{count} {op} scenarios diverged:\n" + string.Join("\n", messages));
    }
}
