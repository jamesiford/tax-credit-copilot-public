using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.Contract;

public sealed class RuntimeResetTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Reset_rotates_only_owned_bytes_and_restarts_independent_id_and_secret_sequences()
    {
        await using var host = await RuntimeRequests.Start();
        await RuntimeRequests.Reset(host);
        var sources = host.App.Services.GetRequiredService<RuntimeSources>();
        var id = sources.NewId();
        var secret = sources.NextBytes(16);
        Assert.EndsWith("000000000004", id.ToString(), StringComparison.Ordinal);
        Assert.Equal(new byte[] { 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1 }, secret);
        var root = host.App.Services.GetRequiredService<RuntimePaths>().Artifacts;
        var sentinel = Path.Combine(root, "not-owned.txt");
        await File.WriteAllTextAsync(sentinel, "synthetic");
        using (var scope = host.App.Services.CreateScope())
        {
            var bytes = scope.ServiceProvider.GetRequiredService<IArtifactByteStore>();
            await bytes.PutAsync("outputs", "synthetic/data.bin", new byte[] { 1, 2 }, "application/octet-stream");
            Assert.Equal(new byte[] { 1, 2 }, await bytes.GetAsync("outputs", "synthetic/data.bin"));
        }
        await RuntimeRequests.Reset(host);
        Assert.Equal(id, sources.NewId());
        Assert.Equal(secret, sources.NextBytes(16));
        using var next = host.App.Services.CreateScope();
        Assert.Null(await next.ServiceProvider.GetRequiredService<IArtifactByteStore>().GetAsync("outputs", "synthetic/data.bin"));
        Assert.Equal("synthetic", await File.ReadAllTextAsync(sentinel));
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task P2_uses_staged_source_catalogue_projector_and_fiscal_rules_then_env_restores_csv()
    {
        await using var host = await RuntimeRequests.Start();
        await RuntimeRequests.Reset(host, "P2");
        var token = await RuntimeRequests.Mint(host, new { });
        using (var response = await RuntimeRequests.Send(host, token, "/api/v2/clients/2001/units"))
        {
            Assert.Equal(200, (int)response.StatusCode);
            var body = await response.Content.ReadFromJsonAsync<JsonElement>();
            Assert.Equal(new long[] { 2001, 2002, 2003, 2004 }, body.GetProperty("accounts").EnumerateArray().Select(e => e.GetInt64()));
            Assert.True(body.GetProperty("rows").GetInt64() > 10000);
            Assert.Equal("lakehouse", body.GetProperty("source").GetString());
        }
        using (var scope = host.App.Services.CreateScope())
        {
            var source = scope.ServiceProvider.GetRequiredService<IClientPayrollSource>();
            var fiscal = source.ClientFiscalWindow(2004, 2023, "begins");
            Assert.False(fiscal.Assumed);
            Assert.NotEqual(new DateOnly(2023, 1, 1), fiscal.Begin);
            Assert.Equal(4, scope.ServiceProvider.GetRequiredService<ISourceReader>().Footprint().Count);
        }
        await RuntimeRequests.Env(host, new { DATA_SOURCE = "csv" });
        using var csv = await RuntimeRequests.Send(host, token);
        Assert.Equal(200, (int)csv.StatusCode);
        Assert.Equal("csv", (await csv.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("source").GetString());
        using var invalid = await host.Client.PostAsJsonAsync("/__contract__/env", new
        {
            set = new Dictionary<string, string> { ["TCC_CONTRACT_HOOKS"] = "0" },
        });
        Assert.Equal(422, (int)invalid.StatusCode);
        Assert.Equal("1", host.App.Services.GetRequiredService<IRuntimeConfiguration>().Get("TCC_CONTRACT_HOOKS"));
    }
}
