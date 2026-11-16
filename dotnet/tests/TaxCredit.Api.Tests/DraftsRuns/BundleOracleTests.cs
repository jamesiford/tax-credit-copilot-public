using System.IO.Compression;
using System.Net.Http.Json;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class BundleOracleTests
{
    [Fact]
    public async Task Every_exported_member_matches_the_python_oracle_including_unicode_numbers_and_review_evidence()
    {
        var fixture = Corpus.Read(Path.Combine("dotnet", "tests", "TaxCredit.Api.Tests", "DraftsRuns", "bundle-oracle.json"));
        var input = (PyDict)PyJson.Loads(fixture.GetProperty("input").GetRawText())!;
        var at = PyDateTime.FromIsoFormat((string)input["at"]!);
        var draft = new ProgramDraft
        {
            DraftId = (string)input["id"]!,
            ProposedCode = (string)input["code"]!,
            Name = (string)input["name"]!,
            State = (string)input["state"]!,
            JurisdictionLevel = "state",
            Status = DraftStatus.ApprovedForExport,
            Version = 1,
            CreatedBy = "ann",
            CreatedAt = at,
            UpdatedBy = "bob",
            UpdatedAt = at,
            Pack = (PyDict)input["pack"]!,
            Years = (PyDict)input["years"]!,
            Validation = (PyDict)input["validation"]!,
            ReviewRequestedBy = "ann",
            Reviewer = "bob",
            Decision = "approve",
            DecidedAt = at,
            ApprovedSha256 = (string)input["content_sha256"]!
        };
        Assert.Equal((string)input["content_sha256"]!, draft.ContentSha256);
        await using var host = await TestHost.Start();
        host.App.Services.GetRequiredService<IProgramDraftRepository>().Create(draft, new DraftEvent
        {
            DraftId = draft.DraftId,
            Seq = 1,
            EventType = "approved",
            Actor = "bob",
            At = at,
            FromStatus = "ready_for_review",
            ToStatus = "approved_for_export"
        });
        using var response = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{draft.DraftId}/export", new { actor = "ann" });
        Assert.True((int)response.StatusCode == 200, await response.Content.ReadAsStringAsync());
        using var archive = new ZipArchive(new MemoryStream(await response.Content.ReadAsByteArrayAsync()));
        var members = fixture.GetProperty("members").EnumerateObject().ToArray();
        Assert.Equal(members.Select(m => m.Name), archive.Entries.Select(e => e.FullName));
        foreach (var member in members)
        {
            using var stream = archive.GetEntry(member.Name)!.Open();
            using var bytes = new MemoryStream();
            stream.CopyTo(bytes);
            Assert.Equal(Encoding.UTF8.GetBytes(member.Value.GetString()!), bytes.ToArray());
        }
    }
}
