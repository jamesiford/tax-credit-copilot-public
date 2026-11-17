using System.IO.Compression;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class DraftTests
{
    [Fact]
    public async Task Approved_saved_content_exports_real_stable_members_and_manifest_hashes()
    {
        await using var host = await TestHost.Start(configuration: new Dictionary<string, string?> { ["PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER"] = "true" });
        var draft = await Create(host);
        var id = draft.GetProperty("draft_id").GetString();
        using var fill = await host.Client.PutAsJsonAsync($"/api/v2/program-drafts/{id}/documents", RecordedBody("second-fill"));
        Assert.Equal(200, (int)fill.StatusCode);
        using var validated = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/validate", new { actor = "ann" });
        Assert.Equal(200, (int)validated.StatusCode);
        var valid = await validated.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(valid.GetProperty("validation").GetProperty("valid").GetBoolean(), valid.ToString());
        using var missingClient = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/preview", new { dataset = "client" });
        Assert.Equal(422, (int)missingClient.StatusCode);
        using var clientData = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/preview", new { dataset = "client", client_id = 1001 });
        Assert.Equal(403, (int)clientData.StatusCode);
        using var request = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/request-review", new { actor = "ann" });
        Assert.Equal(200, (int)request.StatusCode);
        using var self = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/review", new { actor = "ann", decision = "approve" });
        Assert.Equal(422, (int)self.StatusCode);
        using var approved = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/review", new { actor = "bob", decision = "approve" });
        Assert.Equal(200, (int)approved.StatusCode);
        using var exported = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/export", new { actor = "ann" });
        Assert.Equal(200, (int)exported.StatusCode);
        var bytes = await exported.Content.ReadAsByteArrayAsync();
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(bytes)), exported.Headers.GetValues("X-Bundle-Sha256").Single());
        using var zip = new ZipArchive(new MemoryStream(bytes));
        using var manifestStream = zip.GetEntry("manifest.json")!.Open();
        using var manifest = await JsonDocument.ParseAsync(manifestStream);
        foreach (var file in manifest.RootElement.GetProperty("files").EnumerateArray())
        {
            using var member = zip.GetEntry(file.GetProperty("path").GetString()!)!.Open();
            using var output = new MemoryStream();
            member.CopyTo(output);
            Assert.Equal(file.GetProperty("bytes").GetInt64(), output.Length);
            Assert.Equal(file.GetProperty("sha256").GetString(), Convert.ToHexStringLower(SHA256.HashData(output.ToArray())));
        }
        var saved = host.App.Services.GetRequiredService<IProgramDraftRepository>().Get(id!)!;
        using var pack = new StreamReader(zip.GetEntry("rules/zy_draft_jtc.json")!.Open(), Encoding.UTF8);
        var packed = (PyDict)PyJson.Loads(await pack.ReadToEndAsync())!;
        Assert.True(PyEquality.Equal(saved.Pack, packed));
        using var repeated = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/export", new { actor = "ann" });
        Assert.Equal(bytes, await repeated.Content.ReadAsByteArrayAsync());
        using var local = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/export", new { write_local = true });
        Assert.Equal(422, (int)local.StatusCode);
    }

    [Fact]
    public async Task Invalid_scaffold_stale_versions_depth_and_huge_offsets_are_modeled()
    {
        await using var host = await TestHost.Start();
        var draft = await Create(host);
        var id = draft.GetProperty("draft_id").GetString();
        using var validated = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/validate", new { actor = "ann" });
        var current = await validated.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("needs_changes", current.GetProperty("status").GetString());
        Assert.False(current.GetProperty("validation").GetProperty("valid").GetBoolean());
        using var stale = await host.Client.PutAsJsonAsync($"/api/v2/program-drafts/{id}/documents", new { expected_version = 1, pack = new { }, years = new { } });
        Assert.Equal(409, (int)stale.StatusCode);
        object nested = new { };
        for (var n = 0; n < 13; n++) { nested = new { inner = nested }; }
        using var deep = await host.Client.PutAsJsonAsync($"/api/v2/program-drafts/{id}/documents",
            new { expected_version = current.GetProperty("version").GetInt64(), pack = nested, years = new { } });
        Assert.Equal(422, (int)deep.StatusCode);
        const string huge = "99999999999999999999999999999999999999";
        using var page = await host.Client.GetAsync("/api/v2/program-drafts?offset=" + huge);
        var payload = await page.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(200, (int)page.StatusCode);
        Assert.Equal(huge, payload.GetProperty("offset").GetRawText());
        Assert.Equal(1, payload.GetProperty("total").GetInt64());
        Assert.Empty(payload.GetProperty("items").EnumerateArray());
    }

    internal static JsonElement RecordedBody(string id) => File.ReadLines(Path.Combine(Corpus.Root, "contract", "recordings", "p1_program_drafts.jsonl"))
        .Select(line => JsonSerializer.Deserialize<JsonElement>(line)).Single(r => r.GetProperty("id").GetString() == id)
        .GetProperty("request").GetProperty("body").GetProperty("value");

    private static async Task<JsonElement> Create(TestHost host)
    {
        using var response = await host.Client.PostAsJsonAsync("/api/v2/program-drafts", RecordedBody("create"));
        Assert.Equal(201, (int)response.StatusCode);
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }
}
