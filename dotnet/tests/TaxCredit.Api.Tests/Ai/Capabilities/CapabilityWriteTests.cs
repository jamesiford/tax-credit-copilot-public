using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

public sealed class CapabilityWriteTests
{
    private static readonly JsonObject ClaimArgs = new()
    {
        ["client_id"] = 42,
        ["program_code"] = "GA_JTC",
        ["tax_year"] = 2025,
        ["status"] = "proposed",
    };

    [Fact]
    public async Task Prepare_and_commit_require_the_persons_writer_rights_and_record_refusals()
    {
        using var harness = new CapabilityHarness();
        using var person = harness.Principals.Push(new ApiPrincipal(Oid: "reader", Authenticated: true));
        var refusal = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs));
        Assert.Equal(403, refusal.StatusCode);
        Assert.Empty(harness.Confirmations.Rows);
        Assert.Equal("refused", harness.Audit[^1].Fields["outcome"]);
        harness.Writer = true;
        var prepared = await harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        Assert.NotEqual(token, harness.Confirmations.Rows[0].TokenSha256);
        Assert.False(harness.Confirmations.Rows[0].ConsumedAt.HasValue);
        harness.Writer = false;
        Assert.Equal(403, (await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs,
            "key", token))).StatusCode);
        Assert.False(harness.Confirmations.Rows[0].ConsumedAt.HasValue);
    }

    [Fact]
    public async Task Confirmation_binds_person_tool_arguments_and_single_use_while_same_key_replays()
    {
        using var harness = new CapabilityHarness { Writer = true };
        using var person = harness.Principals.Push(new ApiPrincipal(Oid: "writer", Authenticated: true));
        var commits = 0;
        harness.Commit = (_, args) =>
        {
            commits++;
            return Task.FromResult(new JsonObject { ["status"] = args["status"]!.DeepClone(), ["actor"] = "writer" });
        };
        var prepared = await harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        using (harness.Principals.Push(new ApiPrincipal(Oid: "other", Authenticated: true)))
        {
            var other = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token));
            Assert.Equal("confirmation_wrong_user", other.Code);
        }
        var wrongTool = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_transition_commit", ClaimArgs, "key", token));
        Assert.Equal("confirmation_wrong_tool", wrongTool.Code);
        var changed = (JsonObject)ClaimArgs.DeepClone();
        changed["status"] = "assessed";
        var wrongArgs = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", changed, "key", token));
        Assert.Equal("confirmation_wrong_args", wrongArgs.Code);
        var committed = await harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token);
        var replay = await harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token);
        Assert.False(committed["facts"]!["replayed"]!.GetValue<bool>());
        Assert.True(replay["facts"]!["replayed"]!.GetValue<bool>());
        Assert.Equal(1, commits);
        var used = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "other-key", token));
        Assert.Equal("confirmation_replayed", used.Code);
        var second = await harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs);
        var conflict = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs,
            "key", second["facts"]!["confirmation"]!["token"]!.GetValue<string>()));
        Assert.Equal("confirmation_idempotency_conflict", conflict.Code);
    }

    [Fact]
    public async Task Failed_commit_is_consumed_and_cannot_repeat_a_possibly_partial_write()
    {
        using var harness = new CapabilityHarness { Writer = true };
        using var person = harness.Principals.Push(new ApiPrincipal(Oid: "writer"));
        var prepared = await harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        harness.Commit = (_, _) => throw new InvalidOperationException("private implementation detail");
        var error = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token));
        Assert.Equal("internal_error", error.Code);
        Assert.Equal("error", harness.Confirmations.Rows[0].Outcome);
        var replay = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token));
        Assert.Equal("confirmation_replayed", replay.Code);
    }

    [Fact]
    public async Task Timeout_never_promises_a_commit_cannot_land_and_same_key_recovers_the_outcome()
    {
        using var harness = new CapabilityHarness(options: options => options.Timeout = TimeSpan.FromSeconds(1)) { Writer = true };
        using var person = harness.Principals.Push(new ApiPrincipal(Oid: "writer"));
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        harness.Commit = (_, _) => release.Task;
        var prepared = await harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs);
        var token = prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>();
        var timeout = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token));
        Assert.Equal(504, timeout.StatusCode);
        Assert.True(timeout.Retryable);
        Assert.Contains("may still land", timeout.Message);
        release.SetResult(new JsonObject { ["accepted"] = true });
        for (var attempt = 0; attempt < 100 && harness.Confirmations.Rows[0].Outcome != "ok"; attempt++)
        {
            await Task.Delay(10);
        }
        var replay = await harness.Service.InvokeAsync("claim_record_commit", ClaimArgs, "key", token);
        Assert.True(replay["facts"]!["replayed"]!.GetValue<bool>());
    }

    [Fact]
    public void Commit_fields_may_be_outer_or_nested_but_not_contradictory()
    {
        var spec = new CapabilityCatalog().Resolve("claim_record_commit");
        var merged = CapabilityService.MergeCommitArguments(spec, ClaimArgs, "key", "token");
        Assert.True(JsonNode.DeepEquals(ClaimArgs, merged["arguments"]));
        Assert.Equal("key", merged["idempotency_key"]!.GetValue<string>());
        var equivalent = CapabilityService.MergeCommitArguments(spec, merged, "key", "token");
        Assert.True(JsonNode.DeepEquals(merged, equivalent));
        Assert.Throws<CapabilityException>(() => CapabilityService.MergeCommitArguments(spec, merged, "other", "token"));
    }

    [Fact]
    public async Task Cancellation_before_dispatch_never_mints_a_confirmation()
    {
        using var harness = new CapabilityHarness { Writer = true };
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => harness.Service.InvokeAsync("claim_record_prepare", ClaimArgs,
            cancellationToken: cancellation.Token));
        Assert.Empty(harness.Confirmations.Rows);
        Assert.Empty(harness.Audit);
    }
}
