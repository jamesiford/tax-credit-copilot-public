using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using Xunit;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class PackageTests
{
    [Fact]
    public async Task Seeded_package_matches_every_recorded_member_and_download_is_audited()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        var created = await host.Client.PostAsync("/api/clients/1001/packages?tax_year=2025", null);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var package = await created.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, package.GetProperty("rows").GetProperty("Coverage").GetInt32());
        var id = package.GetProperty("artifact_id").GetString();
        Assert.Equal($"/api/clients/1001/artifacts/{id}", created.Headers.Location!.OriginalString);
        var downloaded = await host.Client.GetAsync($"/api/clients/1001/artifacts/{id}");
        Assert.Equal(HttpStatusCode.OK, downloaded.StatusCode);
        var bytes = await downloaded.Content.ReadAsByteArrayAsync();
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(bytes)), downloaded.Headers.GetValues("X-Content-SHA256").Single());
        Assert.True(downloaded.Headers.CacheControl!.NoStore);
        var recorded = File.ReadLines(Path.Combine(Corpus.Root, "contract", "recordings", "p1_artifacts_ai.jsonl"))
            .Select(line => JsonDocument.Parse(line)).Single(d => d.RootElement.GetProperty("id").GetString() == "artifact.download");
        using (recorded)
        using (var zip = new ZipArchive(new MemoryStream(bytes)))
        {
            var expected = recorded.RootElement.GetProperty("response").GetProperty("body").GetProperty("zip_entries").EnumerateArray().ToArray();
            Assert.Equal(expected.Select(e => e.GetProperty("name").GetString()), zip.Entries.Select(e => e.FullName));
            for (var i = 0; i < expected.Length; i++)
            {
                using var buffer = new MemoryStream();
                await zip.Entries[i].Open().CopyToAsync(buffer);
                var member = buffer.ToArray();
                Assert.Equal(expected[i].GetProperty("size").GetInt64(), member.LongLength);
                Assert.Equal(expected[i].GetProperty("sha256").GetString(), Convert.ToHexStringLower(SHA256.HashData(member)));
                var text = Encoding.UTF8.GetString(member);
                Assert.DoesNotContain("employee_id", text, StringComparison.OrdinalIgnoreCase);
                Assert.DoesNotContain("entity_fein", text, StringComparison.OrdinalIgnoreCase);
                Assert.DoesNotContain("record_token", text, StringComparison.OrdinalIgnoreCase);
            }
        }
        using var scope = host.App.Services.CreateScope();
        Assert.Equal("served", Assert.Single(scope.ServiceProvider.GetRequiredService<IArtifactRepository>().Accesses(1001)).Outcome);
    }

    [Fact]
    public async Task Repeat_creation_is_a_new_immutable_generation_and_refusals_are_audited()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        var first = await Create(host.Client);
        var second = await Create(host.Client);
        Assert.NotEqual(first, second);
        Assert.Equal(HttpStatusCode.Forbidden, (await host.Client.GetAsync($"/api/clients/999999/artifacts/{first}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.GetAsync("/api/clients/1001/artifacts/unknown")).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, (await host.Client.PostAsync("/api/clients/999999/packages?tax_year=2025", null)).StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await host.Client.PostAsync("/api/clients/1001/packages", null)).StatusCode);
        using var scope = host.App.Services.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IArtifactRepository>();
        Assert.NotEqual(repository.Find(first)!.BlobPath, repository.Find(second)!.BlobPath);
        Assert.Single(repository.Live(1001, "claim_package", 2025));
        Assert.NotNull(repository.Find(first)!.SupersededAt);
        Assert.Equal("denied", Assert.Single(repository.Accesses(1001)).Outcome);
    }

    private static async Task<string> Create(HttpClient client)
    {
        var response = await client.PostAsync("/api/clients/1001/packages?tax_year=2025", null);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("artifact_id").GetString()!;
    }

    [Fact]
    public async Task Missing_and_corrupt_bytes_are_never_served_and_every_registered_attempt_is_audited()
    {
        await using var host = await TestHost.Start();
        (await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" })).EnsureSuccessStatusCode();
        var id = await Create(host.Client);
        using var scope = host.App.Services.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IArtifactRepository>();
        var template = repository.Find(id)!;
        var missing = repository.Record(template with { ArtifactId = "synthetic-missing", BlobPath = "1001/missing/package.xlsx" });
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.GetAsync($"/api/clients/1001/artifacts/{missing.ArtifactId}")).StatusCode);
        var corrupt = repository.Record(template with { ArtifactId = "synthetic-corrupt", BlobPath = "1001/corrupt/package.xlsx" });
        await scope.ServiceProvider.GetRequiredService<IArtifactByteStore>().PutAsync(corrupt.ContainerName, corrupt.BlobPath,
            Encoding.UTF8.GetBytes("not-the-registered-workbook"), corrupt.ContentType);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await host.Client.GetAsync($"/api/clients/1001/artifacts/{corrupt.ArtifactId}")).StatusCode);
        Assert.Equal(new[] { "missing", "missing" }, repository.Accesses(1001).Select(a => a.Outcome));
    }

    [Fact]
    public async Task Formula_like_attribution_stays_literal_text_and_never_becomes_a_workbook_formula()
    {
        await using var host = await TestHost.Start();
        (await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" })).EnsureSuccessStatusCode();
        using var scope = host.App.Services.CreateScope();
        using var principal = scope.ServiceProvider.GetRequiredService<IApiPrincipalAccessor>().Push(ApiPrincipal.Anonymous);
        var metadata = Assert.IsType<Dictionary<string, object?>>(await scope.ServiceProvider.GetRequiredService<IMediator>()
            .Send(new CreatePackage(1001, 2025, "=1+1")));
        var id = metadata["artifact_id"];
        var downloaded = await host.Client.GetByteArrayAsync($"/api/clients/1001/artifacts/{id}");
        using var zip = new ZipArchive(new MemoryStream(downloaded));
        using (var provenance = new StreamReader(zip.GetEntry("xl/worksheets/sheet4.xml")!.Open()))
        {
            Assert.Contains("<t>=1+1</t>", await provenance.ReadToEndAsync(), StringComparison.Ordinal);
        }
        foreach (var sheet in zip.Entries.Where(e => e.FullName.StartsWith("xl/worksheets/", StringComparison.Ordinal)))
        {
            using var reader = new StreamReader(sheet.Open());
            Assert.DoesNotContain("<f>", await reader.ReadToEndAsync(), StringComparison.Ordinal);
        }
    }
}
