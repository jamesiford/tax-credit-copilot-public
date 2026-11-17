using Microsoft.Agents.AI.Workflows;

namespace TaxCredit.Orchestrator.Workflow;

internal sealed record HeldCommand(
    WriteOwner Owner, WritePrepareRequest Prepare, string Token, string IdempotencyKey, DateTimeOffset ExpiresAt)
{
    public override string ToString() => "HeldCommand { private checkpoint data }";
}

internal enum WriteDecision { Confirm, Cancel, Drop, Recover }
internal sealed record ConfirmationPrompt;
internal sealed record ConfirmationResponse(WriteDecision Decision);

internal sealed class WriteExecutionContext(
    WriteOwner owner, WriteGatewayCall gateway, WriteResultLookup? lookup,
    TimeProvider clock, TimeSpan lifetime)
{
    internal WriteOwner Owner { get; } = owner;
    internal WriteGatewayCall Gateway { get; } = gateway;
    internal WriteResultLookup? Lookup { get; } = lookup;
    internal TimeProvider Clock { get; } = clock;
    internal TimeSpan Lifetime { get; } = lifetime;
    internal WriteResult? Prepared { get; set; }
    internal WriteResult? Completed { get; set; }
}

internal sealed class PrepareExecutor(WriteExecutionContext execution)
    : Executor<WritePrepareRequest>("prepare")
{
    internal const string StateKey = "command";
    internal const string StateScope = "confirmed-write";

    [SendsMessage(typeof(ConfirmationPrompt))]
    public override async ValueTask HandleAsync(
        WritePrepareRequest message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        WriteGatewayReply reply = await execution.Gateway(
            execution.Owner, new(message.Tool, message.Arguments), cancellationToken).ConfigureAwait(false);
        string? token = WriteEnvelope.Token(reply);
        WriteGatewayReply safe = WriteEnvelope.Sanitize(reply, token);
        bool canWait = reply.IsSuccess && token is not null;
        execution.Prepared = new(
            canWait ? WriteStatus.Waiting : WriteStatus.Refused,
            canWait ? "confirmation_required" : WriteEnvelope.Error(safe), safe);
        if (!canWait || token is null)
        {
            return;
        }

        HeldCommand held = new(execution.Owner, message, token, Guid.NewGuid().ToString("N"),
            execution.Clock.GetUtcNow() + execution.Lifetime);
        await context.QueueStateUpdateAsync(StateKey, held, StateScope, cancellationToken).ConfigureAwait(false);
        await context.SendMessageAsync(new ConfirmationPrompt(), cancellationToken).ConfigureAwait(false);
    }
}

internal sealed class CommitExecutor(WriteExecutionContext execution)
    : Executor<ConfirmationResponse>("commit")
{
    [YieldsOutput(typeof(WriteResult))]
    public override async ValueTask HandleAsync(
        ConfirmationResponse message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        HeldCommand? held = await context.ReadStateAsync<HeldCommand>(
            PrepareExecutor.StateKey, PrepareExecutor.StateScope, cancellationToken).ConfigureAwait(false);
        WriteResult result;
        if (held is null || held.Owner != execution.Owner)
        {
            result = new(WriteStatus.NothingPending, "nothing_pending");
        }
        else if (message.Decision is WriteDecision.Cancel or WriteDecision.Drop)
        {
            result = message.Decision == WriteDecision.Cancel
                ? new(WriteStatus.Cancelled, "cancelled") : new(WriteStatus.Dropped, "dropped");
        }
        else if (message.Decision == WriteDecision.Recover)
        {
            result = await RecoverAsync(held, cancellationToken).ConfigureAwait(false);
        }
        else if (execution.Clock.GetUtcNow() >= held.ExpiresAt)
        {
            result = new(WriteStatus.Expired, "expired");
        }
        else
        {
            result = await CommitAsync(held, cancellationToken).ConfigureAwait(false);
        }

        await context.YieldOutputAsync(result,
            result.Status == WriteStatus.Committed ? CancellationToken.None : cancellationToken).ConfigureAwait(false);
    }

    private async Task<WriteResult> CommitAsync(HeldCommand held, CancellationToken cancellationToken)
    {
        WriteGatewayReply reply = await execution.Gateway(execution.Owner,
            new(CommitTool(held), held.Prepare.Arguments, held.IdempotencyKey, held.Token),
            cancellationToken).ConfigureAwait(false);
        string code = WriteEnvelope.Error(reply);
        if (reply.StatusCode == 0 || reply.StatusCode >= 500
            || code is "timeout" or "gateway_unreachable" or "bad_response" or "response_too_large")
        {
            return new(WriteStatus.Unknown, "outcome_unknown");
        }

        return await CompleteAsync(held, reply, cancellationToken).ConfigureAwait(false);
    }

    private async Task<WriteResult> CompleteAsync(
        HeldCommand held, WriteGatewayReply reply, CancellationToken cancellationToken)
    {
        WriteResult result = Outcome(reply, held.Token);
        if (result.Status != WriteStatus.Committed)
        {
            return result;
        }

        execution.Completed = result;
        result = await WritePostCommit.EnrichAsync(execution, held, result, cancellationToken).ConfigureAwait(false);
        execution.Completed = result;
        return result;
    }

    private async Task<WriteResult> RecoverAsync(HeldCommand held, CancellationToken cancellationToken)
    {
        if (execution.Lookup is null)
        {
            return new(WriteStatus.Unknown, "outcome_unknown");
        }

        WriteGatewayReply? reply = await execution.Lookup(execution.Owner,
            new(CommitTool(held), held.Prepare.Arguments, held.IdempotencyKey),
            cancellationToken).ConfigureAwait(false);
        return reply is null ? new(WriteStatus.Unknown, "outcome_unknown")
            : await CompleteAsync(held, reply, cancellationToken).ConfigureAwait(false);
    }

    private static string CommitTool(HeldCommand held) => held.Prepare.Tool[..^8] + "_commit";

    private static WriteResult Outcome(WriteGatewayReply reply, string token)
    {
        WriteGatewayReply safe = WriteEnvelope.Sanitize(reply, token);
        return new(reply.IsSuccess ? WriteStatus.Committed : WriteStatus.Refused,
            reply.IsSuccess ? "ok" : WriteEnvelope.Error(safe), safe);
    }
}
