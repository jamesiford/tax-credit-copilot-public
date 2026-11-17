using System.Text.Json;

namespace TaxCredit.Orchestrator.Workflow;

/// <summary>Verified ownership supplied by the host, never by model arguments.</summary>
public sealed record WriteOwner(string PersonId, string ConversationId);

/// <summary>A canonical, allowlisted prepare tool and its already-settled arguments.</summary>
public sealed record WritePrepareRequest(string Tool, JsonElement Arguments);

/// <summary>Private gateway transport data. Never include this object in a model brief or log.</summary>
public sealed record WriteGatewayRequest(
    string Tool, JsonElement Arguments, string? IdempotencyKey = null, string? ConfirmationToken = null)
{
    /// <inheritdoc />
    public override string ToString() => $"WriteGatewayRequest {{ Tool = {Tool} }}";
}

/// <summary>The gateway's canonical envelope; projection remains the caller's responsibility.</summary>
public sealed record WriteGatewayReply(int StatusCode, JsonElement Body)
{
    /// <summary>Whether the upstream accepted this step.</summary>
    public bool IsSuccess => StatusCode is >= 200 and < 300
        && Body.ValueKind == JsonValueKind.Object && !Body.TryGetProperty("error", out _);
}

/// <summary>A read-only result lookup, not permission to dispatch the command again.</summary>
public sealed record WriteRecoveryRequest(string Tool, JsonElement Arguments, string IdempotencyKey);

/// <summary>Gateway callback used only by the workflow executors.</summary>
public delegate Task<WriteGatewayReply> WriteGatewayCall(
    WriteOwner owner, WriteGatewayRequest request, CancellationToken cancellationToken);

/// <summary>Optional read-only lookup of the original dispatch's idempotent result.</summary>
public delegate Task<WriteGatewayReply?> WriteResultLookup(
    WriteOwner owner, WriteRecoveryRequest request, CancellationToken cancellationToken);

/// <summary>Safe outcomes distinguish a refused write from an uncertain dispatched write.</summary>
public enum WriteStatus
{
    /// <summary>A preview is checkpointed and waiting.</summary>
    Waiting,
    /// <summary>The gateway refused a step.</summary>
    Refused,
    /// <summary>The gateway recorded the change.</summary>
    Committed,
    /// <summary>No workflow belongs to this person and conversation.</summary>
    NothingPending,
    /// <summary>The person explicitly cancelled.</summary>
    Cancelled,
    /// <summary>A different request discarded the preview.</summary>
    Dropped,
    /// <summary>The confirmation window ended.</summary>
    Expired,
    /// <summary>A possible dispatch has no known result and must not be retried.</summary>
    Unknown,
    /// <summary>No confirmable preview could be retained.</summary>
    PrepareFailed,
}

/// <summary>A named, token-free supplementary read for trusted composition.</summary>
public sealed record WriteFollowUp(string Tool, WriteGatewayReply Reply);

/// <summary>A token-free envelope for trusted composition, not raw model narration.</summary>
public sealed record WriteResult(WriteStatus Status, string Code, WriteGatewayReply? Reply = null)
{
    /// <summary>Successful supplementary reads; a missing link never reverses a successful mutation.</summary>
    public IReadOnlyList<WriteFollowUp> FollowUps { get; init; } = [];

    /// <summary>A safe public explanation of a supplementary read failure, when present.</summary>
    public string Note { get; init; } = "";
}
