using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayDownloadTests(GatewayFixture host) : IClassFixture<GatewayFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => host.Reset();
    public Task DisposeAsync() => Task.CompletedTask;
    private async Task<(string Token, JsonObject Link)> Package()
    {
        var token = await host.Token(GatewayFixture.Writer);
        var args = new JsonObject { ["client_id"] = 1001, ["tax_year"] = 2025 };
        var preview = await host.Invoke("claim_package_create_prepare", token, args);
        await host.Invoke("claim_package_create_commit", token, new()
        {
            ["arguments"] = args.DeepClone(),
            ["confirmation_token"] = preview["facts"]!["confirmation"]!["token"]!.DeepClone(),
            ["idempotency_key"] = "gateway-package",
        });
        return (token, await host.Invoke("claim_package_link", token, args));
    }

    [Fact]
    public async Task Real_package_is_person_bound_single_use_and_integrity_checked_over_http()
    {
        var (token, link) = await Package();
        var path = link["facts"]!["download_path"]!.GetValue<string>();
        Assert.StartsWith("/channel/v1/downloads/", path, StringComparison.Ordinal);
        using (var badToken = await host.Send("GET", path, "invalid"))
        { Assert.Equal(HttpStatusCode.Unauthorized, badToken.StatusCode); }
        using (var other = await host.Send("GET", path, await host.Token()))
        { Assert.Equal(HttpStatusCode.Forbidden, other.StatusCode); }
        using var owner = await host.Send("GET", path, token);
        Assert.Equal(HttpStatusCode.OK, owner.StatusCode);
        Assert.Equal("no-store", owner.Headers.CacheControl!.ToString());
        Assert.Equal("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", owner.Content.Headers.ContentType!.MediaType);
        var data = await owner.Content.ReadAsByteArrayAsync();
        var hash = Convert.ToHexStringLower(SHA256.HashData(data));
        Assert.Equal(link["facts"]!["sha256"]!.GetValue<string>(), hash);
        Assert.Equal(hash, owner.Headers.GetValues("X-Content-Sha256").Single());
        Assert.Equal(link["facts"]!["file_name"]!.GetValue<string>(), owner.Content.Headers.ContentDisposition!.FileName!.Trim('"'));
        using var archive = new ZipArchive(new MemoryStream(data), ZipArchiveMode.Read);
        Assert.NotNull(archive.GetEntry("[Content_Types].xml"));
        Assert.NotNull(archive.GetEntry("xl/workbook.xml"));
        Assert.Contains(archive.Entries, entry => entry.FullName.StartsWith("xl/worksheets/", StringComparison.Ordinal));
        using var replay = await host.Send("GET", path, token);
        Assert.Equal(HttpStatusCode.Gone, replay.StatusCode);
        Assert.Equal("confirmation_replayed", (await replay.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.ToString());
        using var scope = host.Services.CreateScope();
        Assert.Equal("served", Assert.Single(scope.ServiceProvider.GetRequiredService<IArtifactRepository>().Accesses(1001)).Outcome);
    }

    [Fact]
    public async Task Simultaneous_possession_based_download_has_one_winner_and_reset_removes_tickets()
    {
        var (_, link) = await Package();
        var path = link["facts"]!["download_path"]!.GetValue<string>();
        var responses = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => host.Send("GET", path)));
        try
        {
            Assert.Single(responses, response => response.StatusCode == HttpStatusCode.OK);
            Assert.Equal(3, responses.Count(response => response.StatusCode == HttpStatusCode.Gone));
        }
        finally { foreach (var response in responses) { response.Dispose(); } }
        await host.Reset();
        using var removed = await host.Send("GET", path);
        Assert.Equal(HttpStatusCode.BadGateway, removed.StatusCode);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Missing_bytes_and_lost_owner_rights_are_audited_and_do_not_restore_a_ticket(bool missing)
    {
        var (token, link) = await Package();
        if (missing)
        {
            using var scope = host.Services.CreateScope();
            var repository = scope.ServiceProvider.GetRequiredService<IArtifactRepository>();
            var artifact = repository.Live(1001, "claim_package", 2025)[0];
            repository.Record(artifact with { ArtifactId = "synthetic-http-missing", BlobPath = "1001/missing/package.xlsx" });
            link = await host.Invoke("claim_package_link", token, new() { ["client_id"] = 1001, ["tax_year"] = 2025 });
        }
        else
        {
            using var change = await host.Client.PostAsJsonAsync("/__contract__/env",
                new { set = new Dictionary<string, string> { ["CLIENT_ALLOWLIST"] = "{}" }, unset = Array.Empty<string>() });
            change.EnsureSuccessStatusCode();
        }
        var path = link["facts"]!["download_path"]!.GetValue<string>();
        using var failure = await host.Send("GET", path);
        Assert.Equal(missing ? HttpStatusCode.NotFound : HttpStatusCode.BadGateway, failure.StatusCode);
        Assert.Equal("download_failed", (await failure.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.ToString());
        using var spent = await host.Send("GET", path);
        Assert.Equal(HttpStatusCode.Gone, spent.StatusCode);
        using var held = host.Services.CreateScope();
        Assert.Equal(missing ? "missing" : "denied",
            Assert.Single(held.ServiceProvider.GetRequiredService<IArtifactRepository>().Accesses(1001)).Outcome);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Unknown_ticket_keeps_the_designed_channel_failure(bool authenticated)
    {
        using var response = await host.Send("GET", "/channel/v1/downloads/not-a-ticket", authenticated ? await host.Token() : null);
        Assert.Equal(HttpStatusCode.BadGateway, response.StatusCode);
        Assert.Equal("invalid_arguments", (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.ToString());
    }
}
