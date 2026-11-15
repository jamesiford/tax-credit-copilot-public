using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS8 (pack validation): replays <c>parity/goldens/pack_validation.jsonl.gz</c>, recorded from the production <c>tools/pack_validation.py</c> on CPython 3.12.
/// The SEMANTIC rules, the registry and year-file checks and every exception are compared bit for bit. The JSON Schema step is a different engine behind
/// <see cref="IJsonSchemaValidator"/>, so it is compared on the accept/reject decision and the distinct (keyword, path) pairs as hard equality, and on wording, count
/// and order as a measured deviation written to <c>docs/pack-validation-deviations.md</c>.
/// </summary>
public sealed class PackValidationParityTests
{
    [Fact]
    public void Every_document_report_matches_python_and_the_schema_step_agrees_on_the_decision()
    {
        var harness = new PackValidationHarness();
        var run = Replay(harness);
        Assert.True(run.Failures.Count == 0, $"{run.Failures.Count}/{run.Total} documents diverged:\n" + string.Join("\n", run.Failures.Take(80)));
        Assert.True(run.Total >= 10000 && run.Errors >= 100 && run.Comparisons.Count(c => c.Python.Count > 0) >= 4000, $"corpus too thin: {run.Total} documents, {run.Errors} exceptions");
        var hard = run.Comparisons.Where(c => !c.DecisionMatches || !c.KeysMatch).Select(c => c.Source.Label).ToList();
        Assert.True(hard.Count == 0, $"{hard.Count} documents diverged on the decision or the (keyword, path) pairs:\n" + string.Join("\n", hard.Take(12)));
    }

    [Fact]
    public void Every_registry_and_file_check_matches_python_over_the_recorded_rule_folders()
    {
        var harness = new PackValidationHarness();
        var failures = new List<string>();
        var reports = 0;
        var errors = 0;
        foreach (var record in PackValidationHarness.Records("all").Concat(PackValidationHarness.Records("pack")))
        {
            var world = (string)record["world"]!;
            var validator = harness.Validator(world);
            string Normalise(string text) => harness.Normalise(text, world);
            IReadOnlyList<PackReport>? actual = null;
            PyException? thrown = null;
            try
            {
                actual = (string)record["k"]! == "all"
                    ? validator.ValidateAll()
                    : [validator.ValidatePack((string)record["path"]!, (bool)record["years"]!)];
            }
            catch (PyException e)
            {
                thrown = e;
            }
            catch (Exception e)
            {
                failures.Add($"#{record["id"]} {record["k"]} {record["world"]}: the port left the recorded path: {e.GetType().Name}: {e.Message}");
                continue;
            }

            var expectedList = record.TryGetValue("reports", out var many) ? (List<object?>)many! : record.TryGetValue("report", out var one) ? [one] : null;
            string? mismatch;
            if (expectedList is null)
            {
                errors++;
                mismatch = thrown is not null && thrown.PythonType == (string)record["err"]! && Normalise(thrown.Message) == (string)record["msg"]! ? null : $"expected {record["err"]}: {record["msg"]}, got {thrown?.PythonType}: {thrown?.Message}";
            }
            else if (thrown is not null)
            {
                mismatch = $"C# raised {thrown.PythonType}: {thrown.Message}";
            }
            else if (expectedList.Count != actual!.Count)
            {
                mismatch = $"{actual.Count} reports, expected {expectedList.Count}: " + string.Join(", ", actual.Select(r => Normalise(r.File)));
            }
            else
            {
                mismatch = null;
                for (var i = 0; i < actual.Count && mismatch is null; i++)
                {
                    reports++;
                    mismatch = PackValidationHarness.CompareReport((PyDict)expectedList[i]!, actual[i], Normalise);
                }
            }

            if (mismatch is not null)
            {
                failures.Add($"#{record["id"]} {record["k"]} {record["world"]} {(record.TryGetValue("path", out var p) ? p : string.Empty)}: {mismatch}");
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count} folder replays diverged:\n" + string.Join("\n", failures.Take(8)));
        Assert.True(reports > 600 && errors >= 8, $"corpus too thin: {reports} reports, {errors} exceptions");
    }

    [Fact]
    public void Deviations_of_the_schema_library_are_measured_and_the_generated_document_is_current()
    {
        var harness = new PackValidationHarness();
        var run = Replay(harness);
        var meta = PackValidationHarness.Meta();
        var semanticIssues = PackValidationHarness.Records("doc").Where(r => r.ContainsKey("report")).Sum(r => ((List<object?>)((PyDict)r["report"]!)["issues"]!).Cast<PyDict>().Count(i => (string)i["code"]! != "schema"));
        var semanticReports = PackValidationHarness.Records("doc").Count(r => r.ContainsKey("report"));
        var text = PackValidationDeviationReport.Build(run.Comparisons, semanticIssues, semanticReports, (string)meta["jsonschema"]!);
        Assert.StartsWith("8.0.5", System.Reflection.CustomAttributeExtensions.GetCustomAttribute<System.Reflection.AssemblyInformationalVersionAttribute>(typeof(Json.Schema.JsonSchema).Assembly)?.InformationalVersion ?? string.Empty, StringComparison.Ordinal);
        if (Environment.GetEnvironmentVariable("TCC_UPDATE_DEVIATIONS") == "1")
        {
            File.WriteAllText(PackValidationDeviationReport.Path, text);
        }

        var onDisk = File.Exists(PackValidationDeviationReport.Path) ? File.ReadAllText(PackValidationDeviationReport.Path).Replace("\r\n", "\n", StringComparison.Ordinal) : string.Empty;
        Assert.True(onDisk == text, "docs/pack-validation-deviations.md is not what the measurement produces; run this test with TCC_UPDATE_DEVIATIONS=1 and review the diff.");
    }

    [Fact]
    public void A_perturbed_report_is_detected_by_the_comparison()
    {
        var harness = new PackValidationHarness();
        var record = PackValidationHarness.Records("doc").First(r => r.ContainsKey("report") && ((List<object?>)((PyDict)r["report"]!)["issues"]!).Cast<PyDict>().Any(i => (string)i["code"]! != "schema"));
        var report = harness.Validator("shipped").ValidateDocument(record["doc"], (string)record["name"]!, (string)record["kind"]!, (bool)record["years"]!);
        var expected = (PyDict)record["report"]!;
        Assert.Null(PackValidationHarness.CompareReport(expected, report, s => s));
        var issues = ((List<object?>)expected["issues"]!).Cast<PyDict>().ToList();
        foreach (var field in new[] { "severity", "code", "path", "message" })
        {
            var changed = new PyDict().Add("file", expected["file"]).Add("kind", expected["kind"]).Add("ok", expected["ok"]);
            var copy = issues.Select(i => { var c = new PyDict(); foreach (var kv in i) { c.Add(kv.Key, kv.Key == field && (string)i["code"]! != "schema" ? (string)kv.Value! + "x" : kv.Value); } return (object?)c; }).ToList();
            changed.Add("issues", copy);
            Assert.True(copy.Cast<PyDict>().Any(i => (string)i["code"]! != "schema") ? PackValidationHarness.CompareReport(changed, report, s => s) is not null : true, field);
        }
    }

    private static Run Replay(PackValidationHarness harness)
    {
        var validator = harness.Validator("shipped");
        var failures = new List<string>();
        var comparisons = new List<SchemaComparison>();
        var total = 0;
        var errors = 0;
        foreach (var record in PackValidationHarness.Records("doc"))
        {
            total++;
            var doc = record["doc"];
            var name = (string)record["name"]!;
            var kind = (string)record["kind"]!;
            var label = $"#{record["id"]} {record["label"]}";
            IReadOnlyList<SchemaFinding> findings;
            try
            {
                findings = harness.Schema.Validate(doc, kind);
            }
            catch (Exception e)
            {
                // A document the schema library cannot be given (or a defect) is a divergence too, never a silent skip.
                failures.Add($"{label}: the schema step left the recorded path: {e.GetType().Name}: {e.Message}");
                continue;
            }

            comparisons.Add(new SchemaComparison(new DocCase(record, PackValidationHarness.Violations(record["schema"])), PackValidationHarness.Violations(findings)));
            PackReport? report = null;
            PyException? thrown = null;
            try
            {
                report = validator.ValidateDocument(doc, name, kind, (bool)record["years"]!);
            }
            catch (PyException e)
            {
                thrown = e;
            }
            catch (Exception e)
            {
                // Outside Python's exception types (a mutant, or a real regression): a divergence too.
                failures.Add($"{label}: the port left the recorded path: {e.GetType().Name}: {e.Message}");
                continue;
            }

            string? mismatch;
            if (record.ContainsKey("err"))
            {
                errors++;
                mismatch = thrown is not null && thrown.PythonType == (string)record["err"]! && thrown.Message == (string)record["msg"]! ? null : $"expected {record["err"]}: {record["msg"]}, got {thrown?.PythonType}: {thrown?.Message}";
            }
            else
            {
                mismatch = thrown is not null ? $"C# raised {thrown.PythonType}: {thrown.Message}" : PackValidationHarness.CompareReport((PyDict)record["report"]!, report!, s => s);
            }

            if (mismatch is not null)
            {
                failures.Add($"{label}: {mismatch}");
            }
        }

        return new Run(total, errors, failures, comparisons);
    }

    private sealed record Run(int Total, int Errors, List<string> Failures, List<SchemaComparison> Comparisons);
}
