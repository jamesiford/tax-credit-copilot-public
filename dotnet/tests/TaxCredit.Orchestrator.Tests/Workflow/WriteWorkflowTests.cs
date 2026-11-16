using System.Reflection;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using TaxCredit.Orchestrator.Workflow;

namespace TaxCredit.Orchestrator.Tests.Workflow;

public sealed class WriteWorkflowTests
{
    private static readonly WriteOwner Owner = new("writer", "conversation");
    private static readonly string[] Allowed = ["engagement_set_prepare"];

    [Fact]
    public async Task GraphUsesSdkRequestPortAndProducesACheckpoint()
    {
        (_, WriteGatewayFake gateway, WriteClock clock) = Create();
        Type executionType = typeof(WriteWorkflow).Assembly.GetType("TaxCredit.Orchestrator.Workflow.WriteExecutionContext")!;
        object execution = Activator.CreateInstance(executionType, Owner, (WriteGatewayCall)gateway.CallAsync,
            (WriteResultLookup)gateway.LookupAsync, clock, TimeSpan.FromMinutes(5))!;
        Type runner = typeof(WriteWorkflow).Assembly.GetType("TaxCredit.Orchestrator.Workflow.WriteCheckpointRunner")!;
        Microsoft.Agents.AI.Workflows.Workflow graph = (Microsoft.Agents.AI.Workflows.Workflow)runner
            .GetMethod("Build", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, [execution])!;
        await using Run run = await InProcessExecution.RunAsync(graph, Request(), CheckpointManager.CreateInMemory());
        Assert.Empty(run.OutgoingEvents.OfType<WorkflowErrorEvent>());
        Assert.Single(run.OutgoingEvents.OfType<RequestInfoEvent>());
        Assert.NotNull(run.LastCheckpoint);
    }

    [Fact]
    public async Task PrepareActuallyPausesInSdkCheckpointAndFreshGraphResumesOnce()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        WriteResult preview = await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.Waiting, preview.Status);
        Assert.Equal("out", preview.Reply!.Body.GetProperty("facts").GetProperty("before").GetString());
        Assert.DoesNotContain(gateway.Token, JsonSerializer.Serialize(preview), StringComparison.Ordinal);
        Assert.DoesNotContain(gateway.Token, gateway.Calls[0].Request.ToString(), StringComparison.Ordinal);
        AssertSdkCheckpoint(flow);
        Assert.Single(gateway.Calls);
        Assert.Equal(0, gateway.Mutations);

        Assert.Equal(WriteStatus.Committed, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(1, gateway.Mutations);
        Assert.Equal(["engagement_set_prepare", "engagement_set_commit"], gateway.Calls.Select(call => call.Request.Tool));
        Assert.All(gateway.Audit, audit => Assert.Equal(Owner, audit.Owner));
        Assert.Equal(2, gateway.Audit.Count);
        WriteGatewayRequest commit = gateway.Calls[1].Request;
        Assert.Equal(gateway.Token, commit.ConfirmationToken);
        Assert.True(Guid.TryParseExact(commit.IdempotencyKey, "N", out _));
        Assert.Equal(gateway.Calls[0].Request.Arguments.GetRawText(), commit.Arguments.GetRawText());
    }

    [Theory]
    [InlineData("confirm", true)]
    [InlineData(" CONFIRM! ", true)]
    [InlineData("Yes, apply.", true)]
    [InlineData("yes apply", true)]
    [InlineData("yes", false)]
    [InlineData("please confirm", false)]
    [InlineData("confirm this", false)]
    [InlineData("why is that?", false)]
    public async Task OnlyExactReaderWordsCanCommit(string text, bool commits)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        Assert.Equal(commits ? WriteStatus.Committed : WriteStatus.Dropped, (await flow.RespondAsync(Owner, text)).Status);
        Assert.Equal(commits ? 1 : 0, gateway.Mutations);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Theory]
    [InlineData("other-writer", "conversation")]
    [InlineData("writer", "another-conversation")]
    public async Task WrongOwnerCannotConsumeOrCommitTheOwnersPreview(string person, string conversation)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(new(person, conversation), "confirm")).Status);
        Assert.Single(gateway.Calls);
        Assert.Equal(WriteStatus.Committed, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Theory]
    [InlineData(299, WriteStatus.Committed)]
    [InlineData(300, WriteStatus.Expired)]
    [InlineData(301, WriteStatus.Expired)]
    public async Task ExpiryUsesExactGreaterThanOrEqualBoundary(int seconds, WriteStatus expected)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, WriteClock clock) = Create();
        await flow.PrepareAsync(Owner, Request());
        clock.Now += TimeSpan.FromSeconds(seconds);
        Assert.Equal(expected, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(expected == WriteStatus.Committed ? 1 : 0, gateway.Mutations);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Fact]
    public async Task CancellationResumesFrameworkWithoutGatewayCommit()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.Cancelled, (await flow.RespondAsync(Owner, "cancel")).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Single(gateway.Calls);
    }

    [Fact]
    public async Task ReaderAuthorizationIsEnforcedAtPreviewAndCannotPause()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        WriteOwner reader = new("reader", "conversation");
        WriteResult result = await flow.PrepareAsync(reader, Request());
        Assert.Equal(WriteStatus.Refused, result.Status);
        Assert.Equal("not_authorized", result.Code);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(reader, "confirm")).Status);
        Assert.Single(gateway.Audit);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task SuccessWithoutValidConfirmationTokenDoesNotPause()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.OmitToken = true;
        Assert.Equal(WriteStatus.Refused, (await flow.PrepareAsync(Owner, Request())).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Single(gateway.Calls);
    }

    [Theory]
    [InlineData("confirmation_expired")]
    [InlineData("confirmation_replayed")]
    [InlineData("confirmation_wrong_user")]
    [InlineData("confirmation_unknown")]
    [InlineData("confirmation_conflict")]
    [InlineData("not_authorized")]
    public async Task GatewayRefusalsRemainVisibleAndAreNeverRetried(string code)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.RefuseCommit = code;
        await flow.PrepareAsync(Owner, Request());
        WriteResult result = await flow.RespondAsync(Owner, "confirm");
        Assert.Equal(WriteStatus.Refused, result.Status);
        Assert.Equal(code, result.Code);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(2, gateway.Calls.Count);
        Assert.Equal(code, gateway.Audit[1].Code);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task GatewayIndependentlyChecksTokenExpiry()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, WriteClock clock) = Create();
        gateway.GatewayLifetime = TimeSpan.FromSeconds(10);
        await flow.PrepareAsync(Owner, Request());
        clock.Now += TimeSpan.FromSeconds(10);
        Assert.Equal("confirmation_expired", (await flow.RespondAsync(Owner, "confirm")).Code);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task RevokedWriterCannotCommitAnEarlierAuthorizedPreview()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        gateway.Writers.Remove(Owner.PersonId);
        Assert.Equal("not_authorized", (await flow.RespondAsync(Owner, "confirm")).Code);
        Assert.Equal(0, gateway.Mutations);
        Assert.Equal("not_authorized", gateway.Audit[1].Code);
    }

    [Fact]
    public async Task GatewayIndependentlyRejectsATokenConsumedElsewhere()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        gateway.ConsumePreview();
        Assert.Equal("confirmation_replayed", (await flow.RespondAsync(Owner, "confirm")).Code);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task GatewayIndependentlyRejectsPreviewArgumentConflict()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        gateway.ChangePreviewArguments(JsonSerializer.SerializeToElement(new { scope = "changed-elsewhere" }));
        Assert.Equal("confirmation_conflict", (await flow.RespondAsync(Owner, "confirm")).Code);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task SharedWorkflowDefinitionsKeepTwoOwnersCheckpointsIsolated()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        WriteOwner other = new("other-writer", Owner.ConversationId);
        await flow.PrepareAsync(Owner, Request());
        await flow.PrepareAsync(other, Request() with { Arguments = JsonSerializer.SerializeToElement(new { scope = "another" }) });
        Assert.Equal(WriteStatus.Committed, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.Committed, (await flow.RespondAsync(other, "confirm")).Status);
        Assert.Equal(2, gateway.Mutations);
        Assert.Equal(Owner, gateway.Calls[2].Owner);
        Assert.Equal(other, gateway.Calls[3].Owner);
    }

    [Fact]
    public async Task CompetingConfirmationsDispatchAtMostOneCommit()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.CommitEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        gateway.ReleaseCommit = new(TaskCreationOptions.RunContinuationsAsynchronously);
        await flow.PrepareAsync(Owner, Request());
        Task<WriteResult> first = flow.RespondAsync(Owner, "confirm");
        await gateway.CommitEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Task<WriteResult> second = flow.RespondAsync(Owner, "confirm");
        gateway.ReleaseCommit.SetResult();
        WriteResult[] outcomes = await Task.WhenAll(first, second);
        Assert.Equal([WriteStatus.Committed, WriteStatus.NothingPending], outcomes.Select(result => result.Status));
        Assert.Equal(1, gateway.Mutations);
        Assert.Equal(2, gateway.Calls.Count);
    }

    [Fact]
    public async Task LostDispatchResponseIsUnknownNeverReconfirmableAndRecoveryUsesOriginalIdentity()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.LoseCommitResponse = true;
        await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.PrepareAsync(Owner, Request())).Status);
        Assert.Equal(1, gateway.Mutations);
        Assert.Equal(2, gateway.Calls.Count);
        Assert.Equal(WriteStatus.Committed, (await flow.RecoverAsync(Owner)).Status);
        Assert.NotNull(gateway.LastLookup);
        Assert.Equal(gateway.Calls[1].Request.IdempotencyKey, gateway.LastLookup.IdempotencyKey);
        Assert.Equal(gateway.Calls[1].Request.Tool, gateway.LastLookup.Tool);
        Assert.Equal(2, gateway.Calls.Count);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Fact]
    public async Task UnknownWriteAllowsOrdinaryReadsWithoutDiscardingRecoveryOrEnablingPrepare()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.LoseCommitResponse = true;
        await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "What is the current trend?")).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.PrepareAsync(Owner, Request())).Status);
        Assert.Equal(2, gateway.Calls.Count);
        Assert.Equal(WriteStatus.Committed, (await flow.RecoverAsync(Owner)).Status);
        Assert.Equal(gateway.Calls[1].Request.IdempotencyKey, gateway.LastLookup!.IdempotencyKey);
        Assert.Equal(1, gateway.Mutations);
        Assert.Equal(2, gateway.Calls.Count);
    }

    [Fact]
    public async Task NonPrepareAndUnknownToolsNeverReachGateway()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        foreach (string tool in new[] { "engagement_set_commit", "unknown_prepare", "client_trend" })
        {
            Assert.Equal(WriteStatus.Refused, (await flow.PrepareAsync(Owner, Request() with { Tool = tool })).Status);
        }

        Assert.Empty(gateway.Calls);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("""{"facts":null}""")]
    [InlineData("""{"facts":{"confirmation":null}}""")]
    [InlineData("""{"facts":{"confirmation":{"token":""}}}""")]
    [InlineData("""{"facts":{"confirmation":{"token":" "}}}""")]
    [InlineData("""{"facts":{"confirmation":{"token":0}}}""")]
    [InlineData("""{"facts":{"confirmation":{"token":{}}}}""")]
    public async Task InvalidPrepareTokenCannotCreateARequest(string body)
    {
        int calls = 0;
        WriteWorkflow flow = new((_, _, _) =>
        {
            calls++;
            return Task.FromResult(new WriteGatewayReply(200, JsonDocument.Parse(body).RootElement.Clone()));
        }, Allowed);
        Assert.Equal(WriteStatus.Refused, (await flow.PrepareAsync(Owner, Request())).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task RefusedGatewayEnvelopeCannotLeakAConfirmationTokenOrCreateARequest()
    {
        const string secret = "synthetic-refused-token";
        WriteWorkflow flow = new((_, _, _) => Task.FromResult(new WriteGatewayReply(403,
            JsonSerializer.SerializeToElement(new
            {
                error = new { code = secret, message = secret },
                facts = new { confirmation = new { token = secret } },
            }))), Allowed);
        WriteResult result = await flow.PrepareAsync(Owner, Request());
        Assert.Equal(WriteStatus.Refused, result.Status);
        Assert.DoesNotContain(secret, JsonSerializer.Serialize(result), StringComparison.Ordinal);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Fact]
    public async Task CommitErrorCodesAndMessagesCannotReflectTheConfirmationToken()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        gateway.RefuseCommit = gateway.Token;
        WriteResult result = await flow.RespondAsync(Owner, "confirm");
        Assert.Equal(WriteStatus.Refused, result.Status);
        Assert.DoesNotContain(gateway.Token, JsonSerializer.Serialize(result), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("timeout")]
    [InlineData("gateway_unreachable")]
    [InlineData("bad_response")]
    [InlineData("response_too_large")]
    public async Task TransportFailureRepliesAfterDispatchRemainUnknownRatherThanDefiniteRefusals(string code)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        gateway.RefuseCommit = code;
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(2, gateway.Calls.Count);
    }

    [Fact]
    public async Task CancellationAfterCommitDispatchLeavesExplicitUnknownAndCannotRetry()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        gateway.CommitEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        gateway.ReleaseCommit = new(TaskCreationOptions.RunContinuationsAsynchronously);
        await flow.PrepareAsync(Owner, Request());
        using CancellationTokenSource cancellation = new();
        Task<WriteResult> committing = flow.RespondAsync(Owner, "confirm", cancellation.Token);
        await gateway.CommitEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await cancellation.CancelAsync();
        Assert.Equal(WriteStatus.Unknown, (await committing).Status);
        Assert.Equal(WriteStatus.Unknown, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(2, gateway.Calls.Count);
    }

    [Fact]
    public async Task PrepareFaultDoesNotMasqueradeAsAHeldPreview()
    {
        WriteWorkflow flow = new((_, _, _) => throw new InvalidOperationException("Synthetic failure."), Allowed);
        Assert.Equal(WriteStatus.PrepareFailed, (await flow.PrepareAsync(Owner, Request())).Status);
        Assert.Equal(WriteStatus.NothingPending, (await flow.RespondAsync(Owner, "confirm")).Status);
    }

    [Theory]
    [InlineData("confirm", WriteStatus.Unknown)]
    [InlineData("cancel", WriteStatus.Cancelled)]
    [InlineData("another question", WriteStatus.Dropped)]
    public async Task MissingFrameworkCheckpointIsExplicitAndNeverRetainsConfirmableState(string text, WriteStatus expected)
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        object slot = Slot(flow);
        PropertyInfo pending = slot.GetType().GetProperty("Pending", BindingFlags.Instance | BindingFlags.NonPublic)!;
        object held = pending.GetValue(slot)!;
        held.GetType().GetProperty("Checkpoint")!.SetValue(held, new CheckpointInfo("missing-session", "missing-checkpoint"));
        Assert.Equal(expected, (await flow.RespondAsync(Owner, text)).Status);
        Assert.NotEqual(WriteStatus.Committed, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Single(gateway.Calls);
        Assert.Equal(0, gateway.Mutations);
    }

    [Fact]
    public async Task AReplacementPreviewCancelsThePreviousFrameworkRequest()
    {
        (WriteWorkflow flow, WriteGatewayFake gateway, _) = Create();
        await flow.PrepareAsync(Owner, Request());
        WritePrepareRequest replacement = Request() with { Arguments = JsonSerializer.SerializeToElement(new { scope = "out_of_scope" }) };
        Assert.Equal(WriteStatus.Waiting, (await flow.PrepareAsync(Owner, replacement)).Status);
        Assert.Equal(WriteStatus.Committed, (await flow.RespondAsync(Owner, "confirm")).Status);
        Assert.Equal(replacement.Arguments.GetRawText(), gateway.Calls[2].Request.Arguments.GetRawText());
        Assert.Equal(1, gateway.Mutations);
    }

    private static (WriteWorkflow, WriteGatewayFake, WriteClock) Create()
    {
        WriteClock clock = new();
        WriteGatewayFake gateway = new(clock);
        return (new(gateway.CallAsync, Allowed, clock, resultLookup: gateway.LookupAsync), gateway, clock);
    }

    private static WritePrepareRequest Request() => new("engagement_set_prepare",
        JsonSerializer.SerializeToElement(new { client_id = 100, program_code = "GA_JTC", scope = "in_scope" }));

    private static void AssertSdkCheckpoint(WriteWorkflow flow)
    {
        // Inspect only the reference boundary, never serialize the private checkpoint payload.
        Type paused = typeof(WriteWorkflow).Assembly.GetType("TaxCredit.Orchestrator.Workflow.PausedWrite")!;
        Assert.Equal(["Storage", "Checkpoint", "RequestId"],
            paused.GetProperties().Select(property => property.Name));
        Assert.Equal(typeof(CheckpointManager), paused.GetProperty("Storage")!.PropertyType);
        Assert.Equal(typeof(CheckpointInfo), paused.GetProperty("Checkpoint")!.PropertyType);
        object slot = Slot(flow);
        object held = slot.GetType().GetProperty("Pending", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(slot)!;
        Assert.NotNull(paused.GetProperty("Checkpoint")!.GetValue(held));
        Assert.DoesNotContain("synthetic-confirmation", held.ToString(), StringComparison.Ordinal);
    }

    private static object Slot(WriteWorkflow flow)
    {
        object slots = typeof(WriteWorkflow).GetField("_slots", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(flow)!;
        return slots.GetType().GetProperty("Item")!.GetValue(slots, [Owner])!;
    }
}
