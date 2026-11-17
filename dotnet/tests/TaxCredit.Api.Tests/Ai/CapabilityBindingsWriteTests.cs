using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using static TaxCredit.Api.Tests.Ai.CapabilityBindingsFixture;

namespace TaxCredit.Api.Tests.Ai;

public sealed class CapabilityBindingsWriteTests
{
    [Theory]
    [InlineData("finding_resolve")]
    [InlineData("finding_reopen")]
    [InlineData("claim_transition")]
    [InlineData("claim_record")]
    [InlineData("engagement_set")]
    [InlineData("base_year_set")]
    [InlineData("claim_package_create")]
    [InlineData("run_batch")]
    public async Task Production_pairs_preview_without_mutation_and_commit_once_across_scopes(string change)
    {
        await using var fixture = await Start();
        if (change == "finding_reopen")
        {
            fixture.Read(provider => provider.GetRequiredService<IFindingRepository>().Record(new FindingResolution
            {
                FindingId = "synthetic-finding",
                ClientId = 1001,
                TaxYear = 2025,
                Resolution = "accept",
                DecidedBy = Writer.Actor,
                DecidedAt = "2026-01-15T12:00:00+00:00",
            }));
        }
        var args = Args(change);
        var before = fixture.State(change);
        var prepared = await fixture.Invoke(change + "_prepare", args);
        Assert.Equal(before, fixture.State(change));
        Assert.NotNull(prepared["facts"]!["preview"]!["after"]);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        var request = Commit(args, token, "synthetic-" + change);
        var wrong = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke(change + "_commit", request, Other));
        Assert.Equal("confirmation_wrong_user", wrong.Code);
        var changed = (JsonObject)args.DeepClone();
        if (change == "run_batch") { changed["kind"] = "assess"; }
        else if (change is "finding_resolve" or "engagement_set") { changed["note"] = "Different"; }
        else if (change == "finding_reopen") { changed["finding_id"] = "other-finding"; }
        else if (change == "base_year_set") { changed["base_year"] = 2025; }
        else { changed["tax_year"] = 2024; }
        var mismatch = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke(change + "_commit", Commit(changed, token, "mismatch")));
        Assert.Equal("confirmation_wrong_args", mismatch.Code);
        Assert.Equal(before, fixture.State(change));
        var committed = await fixture.Invoke(change + "_commit", request);
        Assert.False(committed["facts"]!["replayed"]!.GetValue<bool>());
        var after = fixture.State(change);
        Assert.NotEqual(before, after);
        var replay = await fixture.Invoke(change + "_commit", request);
        Assert.True(replay["facts"]!["replayed"]!.GetValue<bool>());
        Assert.Equal(after, fixture.State(change));
        var events = fixture.Read(provider => provider.GetRequiredService<IChannelAuditRepository>()
            .ForUser(Writer.Oid!, tool: change + "_commit"));
        Assert.Contains(events, row => Equals(row.Fields["outcome"], "ok"));
        Assert.Contains(events, row => Equals(row.Fields["outcome"], "refused"));
    }

    [Theory]
    [InlineData("finding_resolve", """{"client_id":1001,"tax_year":2025,"finding_id":"x","resolution":"assign"}""")]
    [InlineData("claim_record", """{"client_id":1001,"program_code":"GA_JTC","tax_year":2025,"status":"declined"}""")]
    [InlineData("base_year_set", """{"client_id":1001,"unit_id":"GA_ATL_HQ","base_year":2030}""")]
    [InlineData("run_batch", """{"scope":{"kind":"one"}}""")]
    public async Task Invalid_owner_previews_cannot_mint_confirmations(string change, string json)
    {
        await using var fixture = await Start();
        var error = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke(change + "_prepare", JsonNode.Parse(json)!.AsObject()));
        Assert.NotEqual("internal_error", error.Code);
        Assert.DoesNotContain(fixture.Read(provider => provider.GetRequiredService<IChannelAuditRepository>()
            .ForUser(Writer.Oid!, tool: change + "_prepare")), row => Equals(row.Fields["outcome"], "ok"));
    }

    [Fact]
    public async Task Concurrent_commits_cannot_repeat_the_business_command()
    {
        await using var fixture = await Start();
        var args = Args("finding_resolve");
        var prepared = await fixture.Invoke("finding_resolve_prepare", args);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        var request = Commit(args, token, "concurrent");
        var results = await Task.WhenAll(Enumerable.Range(0, 8).Select(async _ =>
        {
            try { return await fixture.Invoke("finding_resolve_commit", request); }
            catch (CapabilityException error) { Assert.Equal("confirmation_replayed", error.Code); return null; }
        }));
        Assert.Contains(results, result => result?["facts"]?["replayed"]?.GetValue<bool>() == false);
        Assert.Single(fixture.Read(provider => provider.GetRequiredService<IFindingRepository>().History(1001, "synthetic-finding")));
        var replay = await fixture.Invoke("finding_resolve_commit", request);
        Assert.True(replay["facts"]!["replayed"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Different_confirmations_with_one_idempotency_key_cannot_both_mutate()
    {
        await using var fixture = await Start();
        var args = Args("finding_resolve");
        var first = await fixture.Invoke("finding_resolve_prepare", args);
        var second = await fixture.Invoke("finding_resolve_prepare", args);
        var results = await Task.WhenAll(new[] { first, second }.Select(async prepared =>
        {
            var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
            try { return await fixture.Invoke("finding_resolve_commit", Commit(args, token, "shared-key")); }
            catch (CapabilityException error) { Assert.Equal("confirmation_idempotency_conflict", error.Code); return null; }
        }));
        Assert.Single(results.OfType<JsonObject>());
        Assert.Single(fixture.Read(provider => provider.GetRequiredService<IFindingRepository>().History(1001, "synthetic-finding")));
    }
}
