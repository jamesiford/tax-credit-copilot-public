using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using Microsoft.Data.SqlClient;
using TaxCredit.Application.Hosting;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Persistence.Tests.Sql;
using Xunit.Abstractions;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

/// <summary>
/// Opt-in (<c>TCC_RUN_BENCH=1</c>): persists synthetic Gold payloads of <c>TCC_BENCH_SIZES</c> (default 100000,400000,1000000)
/// <c>employee_period_fact</c> rows through <see cref="GoldWriter.WriteRun" /> and reports seconds, rows/s and statement count per table.
/// Targets: SQLite always; SQL Server when <c>TCC_SQLSERVER_TEST</c> names an instance (statements, then bulk); the live Warehouse
/// only when <c>TCC_LIVE_PROFILE=yes</c> and <c>az account show</c> succeeds, on a throwaway client that is deleted afterwards.
/// </summary>
public sealed class PersistBench(ITestOutputHelper output)
{
    private sealed record Span(string Name, TimeSpan Duration, IReadOnlyDictionary<string, object?> Tags);

    [Fact]
    [Trait("Category", "bench")]
    public void Gold_payloads_are_timed_per_table_and_target()
    {
        if (Environment.GetEnvironmentVariable("TCC_RUN_BENCH") != "1") { return; }
        var sizes = (Environment.GetEnvironmentVariable("TCC_BENCH_SIZES") ?? "100000,400000,1000000")
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Select(int.Parse).ToArray();
        var directory = Path.Combine(PersistenceFixture.Root, "dotnet", "artifacts", "bench");
        Directory.CreateDirectory(directory);
        var file = Path.Combine(directory, "persist-" + (Environment.GetEnvironmentVariable("TCC_BENCH_LABEL") ?? "run") + ".txt");
        File.Delete(file);
        var targets = new List<string> { "sqlite" };
        if (SqlServerTarget.Configured)
        {
            targets.AddRange(["sqlserver-statements", "sqlserver-bulk"]);
        }

        if (LiveWarehouse.Available)
        {
            targets.AddRange(["warehouse-statements", "warehouse-bulk"]);
        }

        // The statement path is measured only up to this many rows (about 500 rows/s on a SQL Server-family target: 1,000,000 rows is ~35 minutes).
        // Above it the baseline is an estimate, labelled as one. Raise it on purpose with BENCH_STATEMENTS_MAX_ROWS; 0 skips the statement path entirely.
        var statementsMax = long.Parse(Environment.GetEnvironmentVariable("BENCH_STATEMENTS_MAX_ROWS") ?? "400000", CultureInfo.InvariantCulture);
        foreach (var target in targets.Where(x => !x.EndsWith("statements", StringComparison.Ordinal)))
        {
            var text = RetentionCase(target, sizes.Min());
            File.AppendAllText(file, text + "\n");
            output.WriteLine(text);
        }

        foreach (var target in targets)
        {
            foreach (var size in sizes)
            {
                string text;
                if (target.EndsWith("statements", StringComparison.Ordinal) && statementsMax == 0)
                {
                    continue;
                }

                if (target.EndsWith("statements", StringComparison.Ordinal) && size > statementsMax)
                {
                    text = $"=== {target} | {size:N0} employee_period_fact rows | EXTRAPOLATED, NOT MEASURED: about {size / 500.0:N0} s at the measured ~500 rows/s (estimate)\n";
                    File.AppendAllText(file, text + "\n");
                    output.WriteLine(text);
                    continue;
                }

                try { text = Measure(target, size); }
                catch (Exception error) { text = $"=== {target} {size:N0} FAILED: {error.GetType().Name}: {error.Message}\n"; }
                File.AppendAllText(file, text + "\n");
                output.WriteLine(text);
            }
        }
    }

    // Retention: four runs of one size with the newest superseded run kept; the third publication prunes the first, and the pass is timed by its span.
    private static string RetentionCase(string target, int size)
    {
        var spans = new ConcurrentQueue<Span>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == RunSpans.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStopped = activity => spans.Enqueue(new Span(activity.OperationName, activity.Duration, activity.TagObjects.ToDictionary(t => t.Key, t => t.Value))),
        };
        ActivitySource.AddActivityListener(listener);
        var retention = new GoldRetention(1);
        try
        {
            switch (target)
            {
                case "sqlite":
                    using (var fixture = new PersistenceFixture())
                    {
                        WriteSeries(new GoldWriter(fixture.Database, PersistenceFixture.Root, retention: retention), size, 1001);
                    }

                    break;
                case "sqlserver-bulk":
                    using (var sql = SqlServerTarget.TryCreate()!)
                    {
                        WriteSeries(new GoldWriter(sql.Database(BulkLoadPolicy.Default), PersistenceFixture.Root, retention: retention), size, 1001);
                    }

                    break;
                default:
                    var clientId = LiveWarehouse.ThrowawayClient();
                    var database = LiveWarehouse.Database(BulkLoadPolicy.Default);
                    try { WriteSeries(new GoldWriter(database, PersistenceFixture.Root, retention: retention), size, clientId); }
                    finally { LiveWarehouse.Delete(database, clientId); }
                    break;
            }
        }
        catch (Exception error)
        {
            return $"=== retention {target} {size:N0} FAILED: {error.GetType().Name}: {error.Message}\n";
        }

        var prune = spans.Where(s => s.Name == "persist.prune").Select(s => $"{s.Duration.TotalSeconds:F2}s").ToArray();
        return $"=== retention {target} | 4 runs of {size:N0} employee_period_fact rows, keep 1 superseded | prune passes (seconds): {string.Join(", ", prune)}\n";
    }

    private static void WriteSeries(GoldWriter writer, int size, long clientId)
    {
        for (var i = 1; i <= 4; i++)
        {
            var payload = SyntheticGold.Payload(size, "bench-r" + i + "-" + Guid.NewGuid().ToString("N")[..8], clientId);
            var manifest = payload.ManifestRow.ToArray();
            manifest[payload.ManifestColumns.ToList().IndexOf("run_started_at")] = TaxCredit.Domain.Numerics.PyDateTime.FromIsoFormat("2026-03-01T10:0" + i + ":00");
            writer.WriteRun(payload with { ManifestRow = manifest });
        }
    }

    private static string Measure(string target, int size)
    {
        var spans = new ConcurrentQueue<Span>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == RunSpans.SourceName,
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStopped = activity => spans.Enqueue(new Span(activity.OperationName, activity.Duration,
                activity.TagObjects.ToDictionary(t => t.Key, t => t.Value))),
        };
        ActivitySource.AddActivityListener(listener);
        var runId = "bench-" + Guid.NewGuid().ToString("N")[..12];
        var wall = new Stopwatch();
        switch (target)
        {
            case "sqlite":
                using (var fixture = new PersistenceFixture())
                {
                    Run(new GoldWriter(fixture.Database, PersistenceFixture.Root), SyntheticGold.Payload(size, runId), wall);
                }

                break;
            case "sqlserver-statements" or "sqlserver-bulk":
                using (var sql = SqlServerTarget.TryCreate()!)
                {
                    Run(new GoldWriter(sql.Database(target.EndsWith("bulk", StringComparison.Ordinal) ? BulkLoadPolicy.Default : BulkLoadPolicy.Off),
                        PersistenceFixture.Root), SyntheticGold.Payload(size, runId), wall);
                }

                break;
            default:
                var clientId = LiveWarehouse.ThrowawayClient();
                var database = LiveWarehouse.Database(target.EndsWith("bulk", StringComparison.Ordinal) ? BulkLoadPolicy.Default : BulkLoadPolicy.Off);
                try
                {
                    Run(new GoldWriter(database, PersistenceFixture.Root), SyntheticGold.Payload(size, runId, clientId), wall);
                }
                finally
                {
                    LiveWarehouse.Delete(database, clientId);
                }

                break;
        }

        return Render(target, size, spans.ToArray(), wall.Elapsed);
    }

    private static void Run(GoldWriter writer, GoldRunPayload payload, Stopwatch wall)
    {
        wall.Restart();
        writer.WriteRun(payload);
        wall.Stop();
    }

    private static string Render(string target, int size, Span[] spans, TimeSpan wall)
    {
        var text = new StringBuilder();
        var statements = spans.Count(s => s.Name is "sql.insert-batch" or "sql.bulk-copy");
        text.AppendLine(CultureInfo.InvariantCulture, $"=== {target} | {size:N0} employee_period_fact rows | wall {wall.TotalSeconds:F1}s | insert statements/bulk loads {statements:N0} | peak working set so far {Process.GetCurrentProcess().PeakWorkingSet64 / 1048576:N0} MB");
        text.AppendLine("table                    rows        seconds   rows/s   statements");
        foreach (var span in spans.Where(s => s.Name == "persist.insert").OrderBy(s => (string)s.Tags["table"]!))
        {
            var table = (string)span.Tags["table"]!;
            var rows = Convert.ToInt64(span.Tags["rows"], CultureInfo.InvariantCulture);
            var count = spans.Count(s => s.Name is "sql.insert-batch" or "sql.bulk-copy" && (string?)s.Tags["table"] == "tcc_gold." + table);
            var seconds = span.Duration.TotalSeconds;
            text.AppendLine(CultureInfo.InvariantCulture, $"{table,-24} {rows,9:N0} {seconds,10:F2} {(seconds > 0 ? rows / seconds : 0),8:N0} {count,10:N0}");
        }

        foreach (var name in new[] { "persist.retire", "persist.validate", "persist.supersede", "db.commit" })
        {
            text.AppendLine(CultureInfo.InvariantCulture, $"{name,-24} {"",9} {spans.Where(s => s.Name == name).Sum(s => s.Duration.TotalSeconds),10:F2}");
        }

        return text.ToString();
    }
}

/// <summary>The live Warehouse, reached only on explicit opt-in, always through a throwaway client that is removed afterwards.</summary>
internal static class LiveWarehouse
{
    private static readonly string[] Tables =
    [
        "tcc_gold.employee_period_fact", "tcc_gold.employee_eligibility", "tcc_gold.onezero_matrix", "tcc_gold.unit_month_summary",
        "tcc_gold.run_method_summary", "tcc_gold.unit_year_master", "tcc_gold.unit_credit_installment", "tcc_ops.run_manifest",
    ];

    internal static bool Available => Environment.GetEnvironmentVariable("TCC_LIVE_PROFILE") == "yes" && Server is not null && AzLoggedIn();

    private static (string Server, string Database)? Settings { get; } = Read();

    private static string? Server => Settings?.Server;

    internal static long ThrowawayClient() => 9_000_000_000_000L + Random.Shared.NextInt64(1, 999_999);

    internal static PersistenceDatabase Database(BulkLoadPolicy policy)
    {
        var (server, database) = Settings!.Value;
        var builder = new SqlConnectionStringBuilder
        {
            DataSource = server,
            InitialCatalog = database,
            Encrypt = SqlConnectionEncryptOption.Mandatory,
            Pooling = false,
            ConnectTimeout = 90,
        };
        return new PersistenceDatabase(() => new SqlConnection(builder.ConnectionString) { AccessToken = Token() }, new SqlServerDialect(policy));
    }

    /// <summary>Removes only the throwaway client's rows, then proves none remain.</summary>
    internal static void Delete(PersistenceDatabase database, long clientId)
    {
        if (clientId < 9_000_000_000_000L)
        {
            throw new InvalidOperationException("Refusing to delete a client that is not a throwaway.");
        }

        using var session = database.Open();
        foreach (var table in Tables)
        {
            session.Execute(clientId, "DELETE FROM " + table + " WHERE {tenant}");
        }

        foreach (var table in Tables)
        {
            Assert.Empty(session.Query(clientId, "SELECT TOP 1 client_id FROM " + table + " WHERE {tenant}"));
        }
    }

    private static string Token()
    {
        using var process = Process.Start(new ProcessStartInfo("cmd.exe",
            "/c az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv")
        { RedirectStandardOutput = true, UseShellExecute = false })!;
        var token = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        return process.ExitCode == 0 ? token : throw new InvalidOperationException("az could not issue a SQL token.");
    }

    private static bool AzLoggedIn()
    {
        using var process = Process.Start(new ProcessStartInfo("cmd.exe", "/c az account show -o none")
        { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false })!;
        process.WaitForExit();
        return process.ExitCode == 0;
    }

    private static (string, string)? Read()
    {
        string? server = Environment.GetEnvironmentVariable("TCC_LIVE_SQL_SERVER"), database = Environment.GetEnvironmentVariable("TCC_LIVE_SQL_DATABASE");
        if (server is not null && database is not null)
        {
            return (server, database);
        }

        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("TCC_ENV_FILE"),
            Path.Combine(PersistenceFixture.Root, "backend", ".env"),
            Path.Combine(PersistenceFixture.Root, "..", "tax-credit-copilot-public", "backend", ".env"),
        };
        foreach (var path in candidates.Where(File.Exists))
        {
            var values = File.ReadAllLines(path!).Where(l => l.Contains('=', StringComparison.Ordinal) && !l.TrimStart().StartsWith('#'))
                .Select(l => l.Split('=', 2)).GroupBy(p => p[0].Trim()).ToDictionary(g => g.Key, g => g.Last()[1].Trim().Trim('"', '\''));
            if (values.TryGetValue("WAREHOUSE_SERVER", out var s) && values.TryGetValue("WAREHOUSE_DATABASE", out var d))
            {
                return (s, d);
            }
        }

        return null;
    }
}
