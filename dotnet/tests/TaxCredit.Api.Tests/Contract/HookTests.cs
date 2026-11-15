using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Tests.Contract;

public sealed class HookTests
{
    private sealed class Work : IContractWork
    {
        internal string? Profile { get; private set; }
        internal int Changes { get; private set; }
        public ValueTask<int> Drain(CancellationToken cancellationToken) => ValueTask.FromResult(3);
        public ValueTask Reset(string profile, CancellationToken cancellationToken)
        {
            Profile = profile;
            return ValueTask.CompletedTask;
        }

        public ValueTask EnvironmentChanged(CancellationToken cancellationToken)
        {
            Changes++;
            return ValueTask.CompletedTask;
        }
    }

    [Fact]
    public async Task Hooks_call_the_real_ports_and_reset_the_host_local_seams()
    {
        var work = new Work();
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IContractWork>(work));
        var ids = host.App.Services.GetRequiredService<IIdSource>();
        var clock = host.App.Services.GetRequiredService<IClock>();
        var secret = host.App.Services.GetRequiredService<ISecretSource>();
        Assert.Equal(new DateTimeOffset(2026, 1, 15, 12, 0, 0, TimeSpan.Zero), clock.UtcNow);
        var first = ids.NewId();
        var firstSecret = secret.NextBytes(17);
        Assert.NotEqual(first, ids.NewId());
        using var drain = await host.Client.PostAsJsonAsync("/__contract__/drain", new { });
        Assert.Equal("""{"drained":3}""", await drain.Content.ReadAsStringAsync());
        using var env = await host.Client.PostAsJsonAsync("/__contract__/env", new { set = new Dictionary<string, string> { ["Z"] = "2", ["A"] = "1" }, unset = new[] { "Z" } });
        Assert.Equal("""{"set":["A","Z"],"unset":["Z"]}""", await env.Content.ReadAsStringAsync());
        var configuration = host.App.Services.GetRequiredService<IRuntimeConfiguration>();
        Assert.Equal("1", configuration.Get("A"));
        Assert.Null(configuration.Get("Z"));
        Assert.Equal(1, work.Changes);
        using var reset = await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P2" });
        Assert.Equal(200, (int)reset.StatusCode);
        Assert.Equal("P2", work.Profile);
        Assert.Equal(first, ids.NewId());
        Assert.Equal(firstSecret, secret.NextBytes(17));
        Assert.Null(configuration.Get("A"));
    }

    [Fact]
    public async Task Reset_supports_the_unmodified_replay_body_and_explicit_profile_query()
    {
        var work = new Work();
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IContractWork>(work));
        using var defaultReset = await host.Client.PostAsJsonAsync("/__contract__/reset", new { });
        Assert.Equal(200, (int)defaultReset.StatusCode);
        Assert.Equal("P1", work.Profile);
        using var p2Reset = await host.Client.PostAsJsonAsync("/__contract__/reset?profile=P2", new { });
        Assert.Equal("P2", work.Profile);
    }

    [Fact]
    public async Task Mint_signs_the_requested_claims_with_an_ephemeral_rsa_key()
    {
        await using var host = await TestHost.Start();
        using var response = await host.Client.PostAsJsonAsync("/__contract__/mint", new { kind = "agent", roles = new[] { "TCC.Agent" }, exp_in = -7200, claims = new { test = true }, drop = new[] { "iat" } });
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var token = document.RootElement.GetProperty("token").GetString()!.Split('.');
        using var payload = JsonDocument.Parse(Decode(token[1]));
        Assert.Equal("app", payload.RootElement.GetProperty("idtyp").GetString());
        Assert.False(payload.RootElement.TryGetProperty("iat", out _));
        Assert.True(payload.RootElement.GetProperty("test").GetBoolean());
        var clock = host.App.Services.GetRequiredService<IClock>();
        Assert.Equal(clock.UtcNow.ToUnixTimeSeconds() - 7200, payload.RootElement.GetProperty("exp").GetInt64());
        using var rsa = RSA.Create();
        rsa.ImportSubjectPublicKeyInfo(host.App.Services.GetRequiredService<IContractSigningKey>().ExportPublicKey(), out _);
        Assert.True(rsa.VerifyData(Encoding.ASCII.GetBytes(token[0] + "." + token[1]), Decode(token[2]), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1));
    }

    [Fact]
    public async Task Hooks_are_absent_without_the_startup_flag_and_cannot_be_enabled_by_http()
    {
        await using var host = await TestHost.Start(hooks: false);
        foreach (var operation in new[] { "drain", "env", "mint", "reset" })
        {
            using var response = await host.Client.PostAsJsonAsync("/__contract__/" + operation, new { set = new { TCC_CONTRACT_HOOKS = "1" } });
            Assert.Equal(404, (int)response.StatusCode);
        }
    }

    [Fact]
    public async Task Hook_and_request_input_errors_are_json()
    {
        await using var host = await TestHost.Start();
        using var malformed = await host.Client.PostAsync("/__contract__/reset", new StringContent("{"));
        Assert.Equal(422, (int)malformed.StatusCode);
        using var method = await host.Client.GetAsync("/__contract__/reset");
        Assert.Equal(405, (int)method.StatusCode);
        Assert.Contains("POST", method.Content.Headers.Allow);
    }

    private static byte[] Decode(string value)
    {
        var padded = value.Replace('-', '+').Replace('_', '/');
        return Convert.FromBase64String(padded.PadRight((padded.Length + 3) / 4 * 4, '='));
    }
}
