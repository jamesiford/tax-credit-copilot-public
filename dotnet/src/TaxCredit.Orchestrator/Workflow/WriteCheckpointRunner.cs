using Microsoft.Agents.AI.Workflows;

namespace TaxCredit.Orchestrator.Workflow;

internal sealed record PausedWrite(CheckpointManager Storage, CheckpointInfo Checkpoint, string RequestId);

internal sealed class WriteSlot
{
    internal SemaphoreSlim Gate { get; } = new(1, 1);
    internal PausedWrite? Pending { get; set; }
    internal PausedWrite? Recovery { get; set; }
}

internal sealed class WriteCheckpointRunner(
    WriteGatewayCall gateway, WriteResultLookup? lookup, TimeProvider clock, TimeSpan lifetime)
{
    internal async Task<(WriteResult Result, PausedWrite? Pending)> PrepareAsync(
        WriteOwner owner, WritePrepareRequest request, CancellationToken cancellationToken)
    {
        CheckpointManager storage = CheckpointManager.CreateInMemory();
        WriteExecutionContext execution = Context(owner);
        await using Run run = await InProcessExecution.RunAsync(Build(execution),
            request with { Arguments = request.Arguments.Clone() }, storage,
            cancellationToken: cancellationToken).ConfigureAwait(false);
        ThrowOnWorkflowError(run);
        RequestInfoEvent? wait = run.OutgoingEvents.OfType<RequestInfoEvent>().SingleOrDefault();
        if (execution.Prepared?.Status != WriteStatus.Waiting)
        {
            return (execution.Prepared ?? new(WriteStatus.PrepareFailed, "write_flow_failed"), null);
        }

        if (wait is null || run.LastCheckpoint is null)
        {
            return (new(WriteStatus.PrepareFailed, "write_flow_failed"), null);
        }

        return (execution.Prepared, new(storage, run.LastCheckpoint, wait.Request.RequestId));
    }

    internal async Task<WriteResult> ResumeAsync(
        WriteOwner owner, PausedWrite held, WriteDecision decision, CancellationToken cancellationToken)
    {
        WriteExecutionContext execution = Context(owner);
        try
        {
            await using Run run = await InProcessExecution.ResumeAsync(
                Build(execution), held.Checkpoint, held.Storage, cancellationToken).ConfigureAwait(false);
            ExternalRequest request = ExternalRequest.Create(ConfirmationPort(), new ConfirmationPrompt(), held.RequestId);
            await run.ResumeAsync([request.CreateResponse(new ConfirmationResponse(decision))], cancellationToken).ConfigureAwait(false);
            ThrowOnWorkflowError(run);
            return run.OutgoingEvents.OfType<WorkflowOutputEvent>().Select(e => e.Data)
                .OfType<WriteResult>().LastOrDefault() ?? execution.Completed ?? SafeFailure(decision);
        }
        catch (Exception)
        {
            return execution.Completed ?? SafeFailure(decision);
        }
    }

    private static WriteResult SafeFailure(WriteDecision decision) => decision switch
    {
        WriteDecision.Cancel => new(WriteStatus.Cancelled, "cancelled_checkpoint_unavailable"),
        WriteDecision.Drop => new(WriteStatus.Dropped, "dropped_checkpoint_unavailable"),
        _ => new(WriteStatus.Unknown, "outcome_unknown"),
    };

    private WriteExecutionContext Context(WriteOwner owner) => new(owner, gateway, lookup, clock, lifetime);

    private static Microsoft.Agents.AI.Workflows.Workflow Build(WriteExecutionContext execution)
    {
        PrepareExecutor prepare = new(execution);
        RequestPort<ConfirmationPrompt, ConfirmationResponse> wait = ConfirmationPort();
        CommitExecutor commit = new(execution);
        return new WorkflowBuilder(prepare).AddEdge(prepare, wait).AddEdge(wait, commit)
            .WithOutputFrom(commit).Build();
    }

    private static RequestPort<ConfirmationPrompt, ConfirmationResponse> ConfirmationPort() =>
        RequestPort.Create<ConfirmationPrompt, ConfirmationResponse>("await_confirmation");

    private static void ThrowOnWorkflowError(Run run)
    {
        if (run.OutgoingEvents.OfType<WorkflowErrorEvent>().Any())
        {
            throw new InvalidOperationException("The workflow did not complete its step.");
        }
    }
}
