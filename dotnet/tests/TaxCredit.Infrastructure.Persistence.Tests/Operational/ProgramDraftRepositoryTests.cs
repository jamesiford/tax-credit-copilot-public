using TaxCredit.Domain.Numerics;
using System.Numerics;
using TaxCredit.Application.Hosting;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ProgramDraftRepositoryTests
{
    private static readonly PyDateTime Now = RunBatchRepositoryTests.At(0);

    [Fact]
    public void Huge_valid_offsets_keep_the_real_total_without_narrowing_or_allocating()
    {
        using var store = new OperationalDatabase();
        var repository = new ProgramDraftRepository(store.Database);
        repository.Create(Draft(), Event("created"));
        foreach (var offset in new[] { new BigInteger(int.MaxValue) + 1, new BigInteger(long.MaxValue), BigInteger.Pow(10, 100) })
        {
            var page = repository.ListPage(null, 50, offset);
            Assert.Equal(1, page.Total);
            Assert.Empty(page.Items);
        }
        Assert.Throws<ArgumentOutOfRangeException>(() => repository.ListPage(null, 50, -1));
        Assert.Contains("9223372036854775807", new SqlServerDialect().Page("SELECT draft_id FROM tcc_ops.program_draft ORDER BY draft_id", 1, long.MaxValue),
            StringComparison.Ordinal);
    }

    [Fact]
    public void DocumentsHashesStatusesEventsAndListMetadataSurviveReopening()
    {
        using var store = new OperationalDatabase();
        var repository = new ProgramDraftRepository(store.Database);
        var draft = Draft();
        repository.Create(draft, Event("created"));
        var next = draft with
        {
            Version = 2,
            Status = DraftStatus.ReadyForReview,
            UpdatedBy = "reviewer",
            ReviewRequestedBy = "author",
            Reviewer = "reviewer",
            Decision = "approve",
            DecisionComment = "synthetic",
            DecidedAt = Now,
            ApprovedSha256 = draft.ContentSha256,
            ExportSha256 = draft.ContentSha256,
            Validation = new PyDict().Add("ok", true),
        };
        repository.Save(next, 1, Event("edited"));
        var restarted = new ProgramDraftRepository(store.Reopen());
        Assert.Equal(next, restarted.Get("draft"));
        Assert.Equal(draft.ContentSha256, restarted.Get("draft")!.ContentSha256);
        Assert.Equal([1L, 2L], restarted.Events("draft").Select(item => item.Seq).ToArray());
        Assert.Equal(["created", "edited"], restarted.Events("draft").Select(item => item.EventType).ToArray());
        Assert.Equal(next, restarted.LiveForCode("GA_NEW"));
        var page = restarted.ListDrafts("ready_for_review", 1, 0);
        Assert.Equal(1, page.Total);
        Assert.Null(page.Items.Single().Pack);
        Assert.Empty(page.Items.Single().Years);
        Assert.Empty(restarted.ListDrafts(offset: 10).Items);
        Assert.Null(restarted.Get("missing"));
    }

    [Fact]
    public async Task ConcurrentSavesPermitOnlyOneVersionAdvanceAndOneEvent()
    {
        using var store = new OperationalDatabase();
        var first = new ProgramDraftRepository(store.Database);
        var second = new ProgramDraftRepository(store.Reopen());
        var draft = Draft();
        first.Create(draft, Event("created"));
        using var start = new Barrier(2);
        bool Save(ProgramDraftRepository repository, string name)
        {
            start.SignalAndWait();
            try
            {
                repository.Save(draft with { Version = 2, Name = name }, 1, Event("edited"));
                return true;
            }
            catch (DraftConflict)
            {
                return false;
            }
        }

        var results = await Task.WhenAll(Task.Run(() => Save(first, "first")), Task.Run(() => Save(second, "second")));
        Assert.Single(results, result => result);
        Assert.Equal(2, first.Get("draft")!.Version);
        Assert.Equal(2, first.Events("draft").Count);
    }

    [Fact]
    public void OversizedDocumentRollsBackStateDocumentsAndEvent()
    {
        using var store = new OperationalDatabase();
        var repository = new ProgramDraftRepository(store.Database);
        var draft = Draft();
        repository.Create(draft, Event("created"));
        Assert.Throws<ArgumentException>(() => repository.Save(draft with
        {
            Version = 2,
            Pack = new PyDict().Add("content", new string('x', 8001)),
        }, 1, Event("edited")));
        Assert.Equal(draft, repository.Get("draft"));
        Assert.Single(repository.Events("draft"));
    }

    [Fact]
    public void DuplicateLiveCodeAndWrongEventCannotLeavePartialDrafts()
    {
        using var store = new OperationalDatabase();
        var repository = new ProgramDraftRepository(store.Database);
        var draft = Draft();
        repository.Create(draft, Event("created"));
        Assert.Throws<DraftConflict>(() => repository.Create(draft with { DraftId = "other" }, Event("created") with { DraftId = "other" }));
        Assert.Null(repository.Get("other"));
        Assert.Throws<ArgumentException>(() => repository.Save(draft with { Version = 2 }, 1, Event("edited") with { DraftId = "other" }));
        Assert.Equal(1, repository.Get("draft")!.Version);
        repository.Save(draft with { Version = 2, Status = DraftStatus.Withdrawn }, 1, Event("withdrawn"));
        Assert.Null(repository.LiveForCode("GA_NEW"));
    }

    [Fact]
    public void CorruptDocumentHashIsNotSilentlyAccepted()
    {
        using var store = new OperationalDatabase();
        var repository = new ProgramDraftRepository(store.Database);
        repository.Create(Draft(), Event("created"));
        using var session = store.Database.Open();
        session.ExecuteExempt(SqlExemption.Validation, "UPDATE tcc_ops.program_draft_document SET content_json = '{}' WHERE draft_id = ?", "draft");
        Assert.Throws<InvalidDataException>(() => repository.Get("draft"));
    }

    private static ProgramDraft Draft() => new()
    {
        DraftId = "draft",
        ProposedCode = "GA_NEW",
        Name = "Synthetic program",
        JurisdictionLevel = "state",
        State = "GA",
        Status = DraftStatus.Draft,
        Version = 1,
        CreatedBy = "author",
        UpdatedBy = "author",
        CreatedAt = Now,
        UpdatedAt = Now,
        Pack = new PyDict().Add("name", "synthetic").Add("symbol", "\u2603"),
        Years = new PyDict().Add("2023", new PyDict().Add("tax_year", 2023L).Add("value", 3500L)),
    };

    private static DraftEvent Event(string type) => new() { DraftId = "draft", Seq = 99, EventType = type, Actor = "author", At = Now };
}
