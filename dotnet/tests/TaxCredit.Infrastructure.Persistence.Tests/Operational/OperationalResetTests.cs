using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class OperationalResetTests
{
    private static readonly PyDateTime Now = RunBatchRepositoryTests.At(0);

    [Fact]
    [Trait("Category", "heavy")]
    public void P1ResetClearsEveryOperationalTableAndInvalidatesPreResetLeases()
    {
        using var store = new OperationalDatabase();
        var root = OperationalDatabase.Root();
        var importer = new SeedImporter(store.Database, System.IO.Path.Combine(root, "contract", "seed"), root);
        importer.Load("P1");
        Populate(store.Database);
        OperationalSchema.Initialize(store.Database);
        using (var before = store.Database.Open())
        {
            Assert.All(OperationalSchema.TableNames, table => Assert.True(Count(before, table) > 0, table));
        }

        var restored = importer.Load("P1");
        var reopened = store.Reopen();
        using (var after = reopened.Open())
        {
            foreach (var table in OperationalSchema.TableNames)
            {
                var seedName = table[8..] + ".jsonl.gz";
                var expected = restored.TableCounts.GetValueOrDefault("operational/" + seedName)
                    + restored.TableCounts.GetValueOrDefault("ops/" + seedName);
                Assert.Equal(expected, Count(after, table));
            }
        }

        AssertQueueAndChannelEmpty(reopened);
        AssertMetadataAndDecisionsEmpty(reopened);
    }

    private static long Count(SqlSession session, string table) => Convert.ToInt64(
        Assert.Single(session.QueryExempt(SqlExemption.Seed, "SELECT COUNT(*) AS n FROM " + session.Dialect.Name(table)))["n"],
        System.Globalization.CultureInfo.InvariantCulture);

    private static void Populate(PersistenceDatabase database)
    {
        var claims = new ClaimRepository(database);
        claims.Record(ClaimRepositoryTests.Claim(11, "reset-claim"));
        claims.SetEngagement(new ProgramEngagement { ClientId = 11, ProgramCode = "GA_JTC", EffectiveFrom = Now, SetBy = "author", SetAt = Now });
        new ManualOverrideRepository(database).Record(new ManualOverride("reset-override", "reset-run", 11, "unit",
            "GA_JTC:synthetic", "base_year", null, "2023", "reason", "synthetic", "author", Now));
        new RunManifestRepository(database).Record(ManifestOverrideTests.Manifest("reset-run", 11));
        var batches = new RunBatchRepository(database);
        var batch = RunBatchRepositoryTests.Batch("reset-batch");
        batches.Create(batch, RunBatchRepositoryTests.Items(batch, 11, 22));
        Assert.Single(batches.Claim("reset-worker", 1, 120, Now));
        PopulateDraft(database);
        PopulateMetadata(database);
        PopulateChannel(database);
    }

    private static void PopulateDraft(PersistenceDatabase database)
    {
        var draft = new ProgramDraft
        {
            DraftId = "reset-draft",
            ProposedCode = "GA_RESET",
            Name = "Synthetic reset",
            JurisdictionLevel = "state",
            State = "GA",
            Status = DraftStatus.Draft,
            Version = 1,
            CreatedBy = "author",
            UpdatedBy = "author",
            CreatedAt = Now,
            UpdatedAt = Now,
            Pack = new PyDict().Add("name", "synthetic"),
            Years = new PyDict().Add("2023", new PyDict().Add("tax_year", 2023L)),
        };
        new ProgramDraftRepository(database).Create(draft,
            new DraftEvent { DraftId = draft.DraftId, Seq = 0, EventType = "created", Actor = "author", At = Now });
    }

    private static void PopulateMetadata(PersistenceDatabase database)
    {
        var lookups = new LookupStore(database);
        lookups.Put(new LookupEntry("pay_code_category", 11, "code", "RESET", "\"Regular\"", "author"), Now);
        lookups.Put(new LookupEntry("pay_code_category", 0, "code", "RESET", "\"Regular\"", "author"), Now);
        var findings = new FindingRepository(database);
        findings.Record(new FindingResolution
        {
            ClientId = 11,
            FindingId = "reset-finding",
            TaxYear = 2023,
            Resolution = "accept",
            DecidedBy = "author",
            DecidedAt = Now.IsoFormat(),
        });
        Assert.True(findings.Reopen(11, "reset-finding", "reviewer", RunBatchRepositoryTests.At(1)));
        var artifacts = new ArtifactRepository(database);
        artifacts.Record(new ArtifactMetadata
        {
            ArtifactId = "reset-artifact",
            Kind = "claim_package",
            ClientId = 11,
            ProgramCode = "GA_JTC",
            TaxYear = 2023,
            RunId = "reset-run",
            ContainerName = "outputs",
            BlobPath = "11/reset-run/reset.txt",
            FileName = "reset.txt",
            ContentType = "text/plain",
            SizeBytes = 4,
            Sha256 = new string('a', 64),
            CreatedBy = "author",
            CreatedAt = Now,
        });
        artifacts.RecordAccess(new ArtifactAccess("reset-access", "reset-artifact", 11, "synthetic-user", "reset-person", Now, "served"));
    }

    private static void PopulateChannel(PersistenceDatabase database)
    {
        var channel = new ChannelStateRepository(database);
        channel.Grant(new WriterGrant("reset-person", "Synthetic person", "writer", "operator", Now));
        channel.Create(new Confirmation("reset-confirmation", new string('a', 64), "reset-person", "resolve",
            new string('b', 64), Now, RunBatchRepositoryTests.At(60)));
        Assert.True(channel.Consume("reset-confirmation", "reset-person", new string('b', 64), RunBatchRepositoryTests.At(1), "reset-key"));
        channel.RecordResult("reset-confirmation", "ok", "{}");
        var audit = new ChannelAuditRepository(database);
        audit.Append(new ChannelAuditEvent(new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["audit_id"] = "reset-audit",
            ["event_seq"] = 1L,
            ["phase"] = "single",
            ["correlation_id"] = "reset-correlation",
            ["occurred_at"] = Now,
            ["channel"] = "api-test",
            ["user_oid"] = "reset-person",
            ["identity_assurance"] = "delegated",
            ["tool_name"] = "resolve",
            ["action_kind"] = "write_commit",
            ["client_id"] = 11L,
            ["outcome"] = "ok",
            ["numeric_guard"] = "n/a",
            ["is_deterministic_path"] = true,
        }));
        audit.Append(new AgentActionAudit(new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["action_id"] = "reset-action",
            ["agent_name"] = "synthetic-agent",
            ["occurred_at"] = Now,
            ["client_id"] = 11L,
            ["is_deterministic_path"] = true,
        }));
    }

    private static void AssertQueueAndChannelEmpty(PersistenceDatabase database)
    {
        var batches = new RunBatchRepository(database);
        Assert.Null(batches.Get("reset-batch"));
        Assert.Empty(batches.ListItems("reset-batch", null, 10, 0).Items);
        Assert.Empty(batches.ListBatches(10, 0).Items);
        Assert.Empty(batches.Claim("new-worker", 10, 60, RunBatchRepositoryTests.At(2)));
        Assert.Equal(0, batches.QueueHealth(Now).LiveLeases);
        Assert.False(batches.Heartbeat(11, "reset-batch-0", "reset-worker", 120, RunBatchRepositoryTests.At(2)));
        Assert.False(batches.Finish(11, "reset-batch-0", "reset-worker", RunBatchRepositoryTests.At(2),
            new ItemResult { Status = ItemStatus.Succeeded }, "reset-batch"));
        var channel = new ChannelStateRepository(database);
        Assert.False(channel.IsWriter("reset-person"));
        Assert.Empty(channel.Live());
        Assert.Null(channel.FindByTokenHash(new string('a', 64)));
        Assert.Null(channel.FindByIdempotencyKey("reset-person", "reset-key"));
        Assert.False(channel.Consume("reset-confirmation", "reset-person", new string('b', 64), RunBatchRepositoryTests.At(2)));
        Assert.Throws<InvalidOperationException>(() => channel.RecordResult("reset-confirmation", "ok", "{}"));
        var audit = new ChannelAuditRepository(database);
        Assert.Empty(audit.ForUser("reset-person"));
        Assert.Empty(audit.ByCorrelation("reset-correlation"));
        Assert.Empty(audit.Recent());
    }

    private static void AssertMetadataAndDecisionsEmpty(PersistenceDatabase database)
    {
        var drafts = new ProgramDraftRepository(database);
        Assert.Null(drafts.Get("reset-draft"));
        Assert.Null(drafts.LiveForCode("GA_RESET"));
        Assert.Empty(drafts.ListDrafts().Items);
        Assert.Empty(drafts.Events("reset-draft"));
        var findings = new FindingRepository(database);
        Assert.Empty(findings.Live(11));
        Assert.Empty(findings.History(11, "reset-finding"));
        Assert.Empty(findings.Audit(11, "reset-finding"));
        var artifacts = new ArtifactRepository(database);
        Assert.Null(artifacts.Find("reset-artifact"));
        Assert.Empty(artifacts.Live(11));
        Assert.Empty(artifacts.Accesses(11));
        var lookups = new LookupStore(database);
        Assert.Empty(lookups.Entries("pay_code_category", 11));
        Assert.Empty(lookups.Audit(11));
        Assert.Empty(lookups.Audit(0));
        Assert.Empty(new ManualOverrideRepository(database).History(11));
        Assert.Empty(new ManualOverrideRepository(database).BaseYears(11, "GA_JTC"));
        Assert.Null(new RunManifestRepository(database).Get("reset-run"));
        Assert.Null(new ClaimRepository(database).Current(11, "GA_JTC", 2023));
        Assert.Empty(new ClaimRepository(database).Engagements(11));
    }
}
