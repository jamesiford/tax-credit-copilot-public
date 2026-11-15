using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ChannelRepositoryTests
{
    [Fact]
    public void GrantsRevocationAndRegrantSurviveRestartWithoutGrantingAnotherPerson()
    {
        using var store = new OperationalDatabase();
        var repository = new ChannelStateRepository(store.Database);
        var grant = new WriterGrant("person", "Synthetic person", "writer", "operator", RunBatchRepositoryTests.At(0));
        repository.Grant(grant);
        Assert.True(new ChannelStateRepository(store.Reopen()).IsWriter("person"));
        Assert.False(repository.IsWriter("another"));
        Assert.True(repository.Revoke("person", RunBatchRepositoryTests.At(1)));
        Assert.False(repository.Revoke("person", RunBatchRepositoryTests.At(2)));
        Assert.False(repository.IsWriter("person"));
        Assert.Empty(repository.Live());
        repository.Grant(grant with { AddedAt = RunBatchRepositoryTests.At(3) });
        Assert.True(repository.IsWriter("person"));
        Assert.Single(repository.Live());
        Assert.Throws<ArgumentException>(() => repository.Grant(grant with { Role = "reader" }));
    }

    [Fact]
    public async Task ConfirmationIsSingleUseAcrossConnectionsBoundToPersonArgsAndExpiry()
    {
        using var store = new OperationalDatabase();
        var first = new ChannelStateRepository(store.Database);
        var second = new ChannelStateRepository(store.Reopen());
        var confirmation = Token("one", 10);
        first.Create(confirmation);
        Assert.False(first.Consume("one", "another", confirmation.ArgsSha256, RunBatchRepositoryTests.At(1)));
        Assert.False(first.Consume("one", "person", new string('c', 64), RunBatchRepositoryTests.At(1)));
        using var start = new Barrier(2);
        bool Consume(ChannelStateRepository repository)
        {
            start.SignalAndWait();
            return repository.Consume("one", "person", confirmation.ArgsSha256, RunBatchRepositoryTests.At(1), "same-key");
        }

        var results = await Task.WhenAll(Task.Run(() => Consume(first)), Task.Run(() => Consume(second)));
        Assert.Single(results, result => result);
        Assert.NotNull(second.FindByTokenHash(confirmation.TokenSha256)!.ConsumedAt);
        var expired = Token("expired", 2) with { TokenSha256 = new string('d', 64) };
        first.Create(expired);
        Assert.False(second.Consume("expired", "person", expired.ArgsSha256, RunBatchRepositoryTests.At(2)));
        Assert.Null(second.FindByTokenHash(expired.TokenSha256)!.ConsumedAt);
    }

    [Fact]
    public void ConfirmationResultsAreImmutableAndIdempotencyIsRequesterScoped()
    {
        using var store = new OperationalDatabase();
        var repository = new ChannelStateRepository(store.Database);
        var confirmation = Token("one", 10);
        repository.Create(confirmation);
        Assert.Throws<InvalidOperationException>(() => repository.RecordResult("one", "ok", "{}"));
        Assert.True(repository.Consume("one", "person", confirmation.ArgsSha256, RunBatchRepositoryTests.At(1), "key"));
        repository.RecordResult("one", "ok", "{\"recorded\":true}");
        repository.RecordResult("one", "ok", "{\"recorded\":true}");
        Assert.Throws<InvalidOperationException>(() => repository.RecordResult("one", "error", "{}"));
        var restarted = new ChannelStateRepository(store.Reopen());
        Assert.Equal("{\"recorded\":true}", restarted.FindByIdempotencyKey("person", "key")!.ResultJson);
        Assert.Null(restarted.FindByIdempotencyKey("another", "key"));
        Assert.Throws<InvalidOperationException>(() => restarted.Create(confirmation with { ConfirmationId = "duplicate-token" }));
    }

    [Fact]
    public void BeginEndAuditEventsRetainFailuresAndFilterByPersonToolTimeAndCorrelation()
    {
        using var store = new OperationalDatabase();
        var repository = new ChannelAuditRepository(store.Database);
        repository.Append(Event("request", "person", 1, "begin", "pending", 0));
        repository.Append(Event("request", "person", 2, "end", "error", 1));
        repository.Append(Event("other", "another", 1, "single", "ok", 2));
        var restarted = new ChannelAuditRepository(store.Reopen());
        Assert.Equal(2, restarted.ForUser("person").Count);
        Assert.Single(restarted.ForUser("person", since: RunBatchRepositoryTests.At(1), tool: "resolve"));
        Assert.Single(restarted.ForUser("person", until: RunBatchRepositoryTests.At(1)));
        Assert.Equal(["begin", "end"], restarted.ByCorrelation("request").Select(row => row.Fields["phase"]).ToArray());
        Assert.Equal("error", restarted.ByCorrelation("request")[^1].Fields["outcome"]);
        Assert.Single(restarted.ForUser("person", limit: 1));
        Assert.Throws<InvalidOperationException>(() => restarted.Append(Event("request", "person", 1, "begin", "pending", 0)));
    }

    [Fact]
    public void AgentActionAuditIsInsertOnlyWhitelistedAndPaged()
    {
        using var store = new OperationalDatabase();
        var repository = new ChannelAuditRepository(store.Database);
        var fields = new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["action_id"] = "action",
            ["agent_name"] = "synthetic-agent",
            ["occurred_at"] = RunBatchRepositoryTests.At(0),
            ["is_deterministic_path"] = true,
            ["client_id"] = 11L,
            ["prompt_hash"] = new string('a', 64),
        };
        repository.Append(new AgentActionAudit(fields));
        Assert.Single(new ChannelAuditRepository(store.Reopen()).Recent("synthetic-agent", 1));
        Assert.Empty(repository.Recent("another"));
        Assert.Throws<InvalidOperationException>(() => repository.Append(new AgentActionAudit(fields)));
        fields["action_id"] = "another";
        fields["evil_column"] = "should-never-be-sql";
        Assert.Throws<ArgumentException>(() => repository.Append(new AgentActionAudit(fields)));
        Assert.Single(repository.Recent());
    }

    private static Confirmation Token(string id, int expires) => new(id, new string('a', 64), "person", "resolve",
        new string('b', 64), RunBatchRepositoryTests.At(0), RunBatchRepositoryTests.At(expires));

    private static ChannelAuditEvent Event(string id, string user, long sequence, string phase, string outcome, int at) => new(
        new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["audit_id"] = id,
            ["event_seq"] = sequence,
            ["phase"] = phase,
            ["correlation_id"] = id,
            ["occurred_at"] = RunBatchRepositoryTests.At(at),
            ["channel"] = "api-test",
            ["user_oid"] = user,
            ["identity_assurance"] = "delegated",
            ["tool_name"] = "resolve",
            ["action_kind"] = "write_commit",
            ["client_id"] = 11L,
            ["outcome"] = outcome,
            ["numeric_guard"] = "n/a",
            ["is_deterministic_path"] = true,
        });
}
