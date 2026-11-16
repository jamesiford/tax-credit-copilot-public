using System.Diagnostics;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class BatchTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Each_dispatch_uses_current_source_scope_instead_of_capturing_the_mediator_root()
    {
        await using var host = await TestHost.Start();
        host.Client.Timeout = TimeSpan.FromMinutes(5);
        using var first = await host.Client.PostAsJsonAsync("/api/v2/run-batches", new { scope = new { kind = "all" }, dry_run = true });
        Assert.Equal(1, (await first.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("preview").GetProperty("clients").GetInt64());
        await RuntimeRequests.Reset(host, "P2");
        using var second = await host.Client.PostAsJsonAsync("/api/v2/run-batches", new { scope = new { kind = "all" }, dry_run = true });
        Assert.Equal(202, (int)second.StatusCode);
        Assert.Equal(4, (await second.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("preview").GetProperty("clients").GetInt64());
    }

    [Fact]
    public async Task Dry_run_enqueues_nothing_and_acceptance_is_requester_key_idempotent()
    {
        await using var host = await TestHost.Start();
        using var preview = await host.Client.PostAsJsonAsync("/api/v2/run-batches", Body(dry: true));
        Assert.Equal(202, (int)preview.StatusCode);
        Assert.True((await preview.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("dry_run").GetBoolean());
        var queue = host.App.Services.GetRequiredService<IRunBatchRepository>();
        Assert.Equal(0, queue.ListBatches(10, 0).Total);
        var first = await Accept(host);
        using var repeated = await host.Client.PostAsJsonAsync("/api/v2/run-batches", new
        {
            idempotency_key = "synthetic-acceptance",
            kind = "assess",
            scope = new { kind = "one", client_ids = new[] { 2002 } },
        });
        Assert.Equal(202, (int)repeated.StatusCode);
        var again = await repeated.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(first.GetProperty("batch_id").GetString(), again.GetProperty("batch_id").GetString());
        Assert.True(again.GetProperty("idempotent_replay").GetBoolean());
        Assert.Equal(1, queue.ListBatches(10, 0).Total);
        var id = first.GetProperty("batch_id").GetString();
        using var cancel = await host.Client.PostAsJsonAsync($"/api/v2/run-batches/{id}/cancel", new { });
        Assert.Equal(1, (await cancel.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("cancelled_now").GetInt64());
        using var retry = await host.Client.PostAsJsonAsync($"/api/v2/run-batches/{id}/retry-failed", new { });
        Assert.Equal(0, (await retry.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("requeued").GetInt64());
        Assert.Equal(BatchStatus.Cancelled, queue.Get(id!)!.Status);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Http_accepted_work_completes_in_finite_worker_and_reopen_retains_one_publication()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var accepted = await Accept(host);
        var batchId = accepted.GetProperty("batch_id").GetString()!;
        var paths = host.App.Services.GetRequiredService<RuntimePaths>();
        using var worker = Launch(paths);
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        try { await worker.WaitForExitAsync(timeout.Token); }
        finally { if (!worker.HasExited) { worker.Kill(entireProcessTree: true); } }
        Assert.Equal(0, worker.ExitCode);
        var database = PersistenceDatabase.Sqlite(paths.Database);
        var queue = new RunBatchRepository(database);
        var item = queue.ListItems(batchId, null, 10, 0).Items.Single();
        Assert.True(item.Status == ItemStatus.Succeeded, $"{item.Status}: {item.ErrorDependency}/{item.ErrorMessage}");
        Assert.Equal(BatchStatus.Succeeded, queue.Get(batchId)!.Status);
        var manifests = new RunManifestRepository(database);
        Assert.Equal("success", manifests.Get(item.RunId!)!.RunStatus);
        using var session = database.Open();
        Assert.NotEmpty(session.Query(1001, "SELECT run_id FROM tcc_gold.employee_eligibility WHERE {tenant} AND run_id=?", item.RunId));
        Assert.NotEmpty(session.Query(1001, "SELECT claim_id FROM tcc_ops.program_claim WHERE {tenant} AND tax_year=?", 2025));
        var count = manifests.Count();
        _ = await Accept(host);
        using var drain = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal(0, (await drain.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("drained").GetInt64());
        Assert.Equal(count, manifests.Count());
    }

    internal static async Task<JsonElement> Accept(TestHost host)
    {
        using var accepted = await host.Client.PostAsJsonAsync("/api/v2/run-batches", Body());
        Assert.True((int)accepted.StatusCode == 202, await accepted.Content.ReadAsStringAsync());
        return await accepted.Content.ReadFromJsonAsync<JsonElement>();
    }

    private static object Body(bool dry = false) => new
    {
        dry_run = dry,
        kind = "calculate",
        scope = new { kind = "one", client_ids = new[] { 1001 } },
        program_code = "GA_JTC",
        tax_years = new[] { 2025 },
        force = true,
        idempotency_key = "synthetic-acceptance",
    };

    private static Process Launch(RuntimePaths paths)
    {
        var dll = Path.Combine(Corpus.Root, "dotnet", "artifacts", "bin", "TaxCredit.Worker", "debug", "TaxCredit.Worker.dll");
        var start = new ProcessStartInfo("dotnet") { WorkingDirectory = Path.Combine(Corpus.Root, "dotnet"), RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add(dll);
        start.ArgumentList.Add("--once");
        foreach (var (key, value) in new Dictionary<string, string>
        {
            ["TCC_CONTRACT_HOOKS"] = "0",
            ["ENVIRONMENT"] = "local",
            ["AUTH_MODE"] = "none",
            ["DATA_SOURCE"] = "csv",
            ["TCC_PERSISTENCE_PROVIDER"] = "sqlite",
            ["OPERATIONAL_DB"] = paths.Database,
            ["ARTIFACT_STORE"] = "local",
            ["ARTIFACT_LOCAL_ROOT"] = paths.Artifacts,
            ["FOUNDRY_PROJECT_ENDPOINT"] = "",
            ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "",
            ["TCC_FEATURE_ASSEMBLIES"] = "",
            ["TCC_REPOSITORY_ROOT"] = Corpus.Root,
        }) { start.Environment[key] = value; }
        var process = Process.Start(start)!;
        process.OutputDataReceived += (_, _) => { };
        process.ErrorDataReceived += (_, _) => { };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return process;
    }
}
