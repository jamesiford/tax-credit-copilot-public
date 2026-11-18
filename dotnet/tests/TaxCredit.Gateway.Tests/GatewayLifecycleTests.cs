using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayLifecycleTests
{
    [Fact]
    public async Task Expired_ledger_and_session_cannot_supply_another_answer()
    {
        var clock = new ManualClock();
        await using var host = new GatewayFixture(services =>
        {
            services.RemoveAll<TimeProvider>();
            services.AddSingleton<TimeProvider>(clock);
        });
        await host.InitializeAsync();
        var token = await host.Token();
        await host.Invoke("client_situation", token, new() { ["client_id"] = 1001 });
        var (session, _) = await host.Initialize(token);
        clock.Advance(TimeSpan.FromHours(8));
        var check = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 1001" });
        Assert.Equal("rejected", check["facts"]!["status"]!.ToString());
        using var expired = await host.Rpc(token, session, new { jsonrpc = "2.0", id = 2, method = "tools/list" });
        Assert.Equal(HttpStatusCode.NotFound, expired.StatusCode);
    }

    [Fact]
    public async Task Hooks_off_composition_has_no_control_routes_even_in_local_development()
    {
        var directory = Path.Combine(AppContext.BaseDirectory, "gateway-deployed-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(directory);
            await using var app = GatewayHost.Build(
            [
                "--urls=http://127.0.0.1:0", "--CONTRACT_HOOKS=0", "--ENVIRONMENT=local", "--AUTH_MODE=none",
                "--AUTH_TENANT_ID=" + GatewayFixture.Tenant, "--GATEWAY_AUDIENCE=api://synthetic-channel", "--API_AUDIENCE=api://synthetic-api",
                "--OPERATIONAL_DB=" + Path.Combine(directory, "operations.db"), "--ARTIFACT_LOCAL_ROOT=" + Path.Combine(directory, "bytes"),
            ], builder => builder.Logging.ClearProviders());
            await app.StartAsync();
            var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            using var client = new HttpClient { BaseAddress = new Uri(address) };
            foreach (var route in new[] { "reset", "drain", "env", "mint" })
            {
                using var response = await client.PostAsJsonAsync("/__contract__/" + route, new { });
                Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
            }
            using var health = await client.GetAsync("/api/health");
            Assert.Equal(HttpStatusCode.OK, health.StatusCode);
            using var anonymous = await client.GetAsync("/channel/v1/tools");
            Assert.Equal(HttpStatusCode.Unauthorized, anonymous.StatusCode);
        }
        finally
        {
            Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
            if (Directory.Exists(directory)) { Directory.Delete(directory, true); }
        }
    }

    private sealed class ManualClock : TimeProvider
    {
        private long _ticks;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        public override long GetTimestamp() => Interlocked.Read(ref _ticks);
        public override DateTimeOffset GetUtcNow() => new DateTimeOffset(2026, 1, 15, 12, 0, 0, TimeSpan.Zero).AddTicks(GetTimestamp());
        public void Advance(TimeSpan by) => Interlocked.Add(ref _ticks, by.Ticks);
    }
}
