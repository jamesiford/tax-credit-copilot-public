using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.Contract;

public sealed class ExecutableTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task A_real_finite_Worker_process_consumes_the_API_composed_database()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        RuntimeQueueTests.Enqueue(host, "process");
        var paths = host.App.Services.GetRequiredService<RuntimePaths>();
        using var process = Launch("Worker", paths.Database, paths.Artifacts, "--once");
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        try { await process.WaitForExitAsync(timeout.Token); }
        finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); } }
        Assert.Equal(0, process.ExitCode);
        RuntimeQueueTests.VerifyPublication(host, "process");
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task The_ordinary_API_executable_opens_a_real_socket_with_hooks_absent()
    {
        var root = Directory.CreateDirectory(Path.Combine(Corpus.Root, "dotnet", "artifacts", "executable-tests", Guid.NewGuid().ToString("N"))).FullName;
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        using var process = Launch("Api", Path.Combine(root, "operations.db"), Path.Combine(root, "bytes"), "--urls=http://127.0.0.1:" + port);
        try
        {
            using var client = new HttpClient(new HttpClientHandler { UseProxy = false })
            { BaseAddress = new Uri("http://127.0.0.1:" + port), Timeout = TimeSpan.FromSeconds(2) };
            await WaitForHealth(client, process);
            using var ready = await client.GetAsync("/api/ready");
            Assert.Equal(200, (int)ready.StatusCode);
            Assert.True((await ready.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("ready").GetBoolean());
            using var hook = await client.PostAsJsonAsync("/__contract__/reset", new { });
            Assert.Equal(404, (int)hook.StatusCode);
        }
        finally
        {
            if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(); }
            Directory.Delete(root, recursive: true);
        }
    }

    private static Process Launch(string host, string database, string artifacts, string argument)
    {
        var dll = Path.Combine(Corpus.Root, "dotnet", "artifacts", "bin", "TaxCredit." + host, "debug", "TaxCredit." + host + ".dll");
        Assert.True(File.Exists(dll), "Build the solution before executable tests.");
        var start = new ProcessStartInfo("dotnet") { WorkingDirectory = Path.Combine(Corpus.Root, "dotnet"), RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add(dll);
        start.ArgumentList.Add(argument);
        foreach (var (key, value) in new Dictionary<string, string>
        {
            ["CONTRACT_HOOKS"] = "0",
            ["ENVIRONMENT"] = "local",
            ["AUTH_MODE"] = "none",
            ["DATA_SOURCE"] = "csv",
            ["PERSISTENCE_PROVIDER"] = "sqlite",
            ["OPERATIONAL_DB"] = database,
            ["ARTIFACT_STORE"] = "local",
            ["ARTIFACT_LOCAL_ROOT"] = artifacts,
            ["FOUNDRY_PROJECT_ENDPOINT"] = "",
            ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "",
            ["FEATURE_ASSEMBLIES"] = "",
            ["REPOSITORY_ROOT"] = Corpus.Root,
        }) { start.Environment[key] = value; }
        var process = Process.Start(start)!;
        process.OutputDataReceived += (_, _) => { };
        process.ErrorDataReceived += (_, _) => { };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return process;
    }

    private static async Task WaitForHealth(HttpClient client, Process process)
    {
        for (var n = 0; n < 100; n++)
        {
            Assert.False(process.HasExited, "The executable exited before readiness.");
            try
            {
                using var response = await client.GetAsync("/api/health");
                if (response.IsSuccessStatusCode) { return; }
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            await Task.Delay(100);
        }
        Assert.Fail("The API did not open its socket before the startup deadline.");
    }
}
