using System.Text.Json;
using TaxCredit.Orchestrator.Workflow;

namespace TaxCredit.Orchestrator.Tests.Workflow;

public sealed class WritePostCommitTests
{
    private static readonly WriteOwner Owner = new("writer", "package-conversation");
    private static readonly string[] PackageTools = ["claim_package_create_prepare"];

    [Fact]
    public async Task PackageCommitFetchesSanitizedLinkOnceUsingOnlyOriginalHeldScope()
    {
        PackageRig rig = new();
        await rig.Flow.PrepareAsync(Owner, PackageRequest());
        WriteResult result = await rig.Flow.RespondAsync(Owner, "confirm");
        Assert.Equal(WriteStatus.Committed, result.Status);
        Assert.True(result.Reply!.Body.GetProperty("facts").GetProperty("recorded").GetBoolean());
        WriteFollowUp link = Assert.Single(result.FollowUps);
        Assert.Equal("claim_package_link", link.Tool);
        Assert.Equal("gateway-download", link.Reply.Body.GetProperty("facts").GetProperty("link").GetString());
        Assert.DoesNotContain(rig.Gateway.Token, JsonSerializer.Serialize(result), StringComparison.Ordinal);
        Assert.Empty(result.Note);
        Assert.Equal(["claim_package_create_prepare", "claim_package_create_commit", "claim_package_link"],
            rig.Calls.Select(call => call.Tool));
        WriteGatewayRequest lookup = rig.Calls[2];
        Assert.Equal(100, lookup.Arguments.GetProperty("client_id").GetInt32());
        Assert.Equal(2030, lookup.Arguments.GetProperty("tax_year").GetInt32());
        Assert.Equal(2, lookup.Arguments.EnumerateObject().Count());
        Assert.Null(lookup.ConfirmationToken);
        Assert.Null(lookup.IdempotencyKey);
        Assert.Equal(WriteStatus.NothingPending, (await rig.Flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Equal(3, rig.Calls.Count);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LinkFailurePreservesCommittedMutationAndReportsPublicNoteWithoutRetry(bool throws)
    {
        PackageRig rig = new(_ => throws
            ? throw new TimeoutException("Synthetic link failure.")
            : Task.FromResult(new WriteGatewayReply(503,
                JsonSerializer.SerializeToElement(new { error = new { code = "link_unavailable" } }))));
        await rig.Flow.PrepareAsync(Owner, PackageRequest());
        WriteResult result = await rig.Flow.RespondAsync(Owner, "confirm");
        Assert.Equal(WriteStatus.Committed, result.Status);
        Assert.NotNull(result.Reply);
        Assert.Empty(result.FollowUps);
        Assert.Equal("The package was built, but its link is unavailable.", result.Note);
        Assert.Equal(1, rig.Gateway.Mutations);
        await rig.Flow.RespondAsync(Owner, "confirm");
        Assert.Equal(3, rig.Calls.Count);
    }

    [Fact]
    public async Task CancellationWhileFetchingLinkCannotEraseKnownSuccessfulMutation()
    {
        using CancellationTokenSource cancellation = new();
        TaskCompletionSource readStarted = new(TaskCreationOptions.RunContinuationsAsynchronously);
        PackageRig rig = new(async ct =>
        {
            readStarted.SetResult();
            await Task.Delay(Timeout.InfiniteTimeSpan, ct);
            throw new InvalidOperationException("The read should end through cancellation.");
        });
        await rig.Flow.PrepareAsync(Owner, PackageRequest());
        Task<WriteResult> confirming = rig.Flow.RespondAsync(Owner, "confirm", cancellation.Token);
        await readStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(1, rig.Gateway.Mutations);
        await cancellation.CancelAsync();
        WriteResult result = await confirming.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(WriteStatus.Committed, result.Status);
        Assert.Contains("built", result.Note, StringComparison.Ordinal);
        Assert.Contains("unavailable", result.Note, StringComparison.Ordinal);
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Equal(WriteStatus.NothingPending, (await rig.Flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(3, rig.Calls.Count);
    }

    [Fact]
    public async Task RefusedCommitNeverFetchesPackageLink()
    {
        PackageRig rig = new();
        rig.Gateway.RefuseCommit = "confirmation_conflict";
        await rig.Flow.PrepareAsync(Owner, PackageRequest());
        WriteResult result = await rig.Flow.RespondAsync(Owner, "confirm");
        Assert.Equal(WriteStatus.Refused, result.Status);
        Assert.Empty(result.FollowUps);
        Assert.Empty(result.Note);
        Assert.Equal(["claim_package_create_prepare", "claim_package_create_commit"], rig.Calls.Select(call => call.Tool));
        Assert.Equal(0, rig.Gateway.Mutations);
    }

    [Fact]
    public async Task UnknownCommitDoesNotFetchLinkUntilReadOnlyRecoveryEstablishesSuccess()
    {
        PackageRig rig = new();
        rig.Gateway.LoseCommitResponse = true;
        await rig.Flow.PrepareAsync(Owner, PackageRequest());
        Assert.Equal(WriteStatus.Unknown, (await rig.Flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(2, rig.Calls.Count);
        WriteResult recovered = await rig.Flow.RecoverAsync(Owner);
        Assert.Equal(WriteStatus.Committed, recovered.Status);
        Assert.Single(recovered.FollowUps);
        Assert.Equal(3, rig.Calls.Count);
        Assert.Single(rig.Calls, call => call.Tool == "claim_package_create_commit");
        Assert.Equal(1, rig.Gateway.Mutations);
    }

    private static WritePrepareRequest PackageRequest() => new("claim_package_create_prepare",
        JsonSerializer.SerializeToElement(new { client_id = 100, tax_year = 2030, note = "not forwarded to link" }));

    private sealed class PackageRig
    {
        internal WriteGatewayFake Gateway { get; } = new(new WriteClock());
        internal List<WriteGatewayRequest> Calls { get; } = [];
        internal WriteWorkflow Flow { get; }

        internal PackageRig(Func<CancellationToken, Task<WriteGatewayReply>>? link = null)
        {
            Flow = new(async (owner, request, ct) =>
            {
                Calls.Add(request);
                return request.Tool == "claim_package_link" && link is not null
                    ? await link(ct) : await Gateway.CallAsync(owner, request, ct);
            }, PackageTools, new WriteClock(), resultLookup: Gateway.LookupAsync);
        }
    }
}
