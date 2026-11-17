using System.Collections.Concurrent;

namespace TaxCredit.Orchestrator.Workflow;

/// <summary>
/// Runs prepare/request/commit across real in-memory SDK checkpoints. The model may only call PrepareAsync;
/// the host routes exact reader responses to RespondAsync. Result recovery is explicitly read-only.
/// </summary>
public sealed class WriteWorkflow
{
    private readonly ConcurrentDictionary<WriteOwner, WriteSlot> _slots = new();
    private readonly HashSet<string> _allowed;
    private readonly WriteCheckpointRunner _runner;

    /// <summary>Allowlisting is supplied from the canonical catalogue, never from a model's proposed name.</summary>
    public WriteWorkflow(
        WriteGatewayCall gateway, IEnumerable<string> allowedPrepareTools, TimeProvider? clock = null,
        TimeSpan? confirmationLifetime = null, WriteResultLookup? resultLookup = null)
    {
        ArgumentNullException.ThrowIfNull(gateway);
        ArgumentNullException.ThrowIfNull(allowedPrepareTools);
        _allowed = new(allowedPrepareTools, StringComparer.Ordinal);
        if (_allowed.Any(tool => !tool.EndsWith("_prepare", StringComparison.Ordinal)))
        {
            throw new ArgumentException("Only canonical prepare tools may enter the workflow.", nameof(allowedPrepareTools));
        }

        TimeSpan lifetime = confirmationLifetime ?? TimeSpan.FromMinutes(5);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(lifetime, TimeSpan.Zero, nameof(confirmationLifetime));
        _runner = new(gateway, resultLookup, clock ?? TimeProvider.System, lifetime);
    }

    /// <summary>A new preview drops an older one. An unresolved dispatched write cannot become confirmable again.</summary>
    public async Task<WriteResult> PrepareAsync(
        WriteOwner owner, WritePrepareRequest request, CancellationToken cancellationToken = default)
    {
        ValidateOwner(owner);
        ArgumentNullException.ThrowIfNull(request);
        if (!_allowed.Contains(request.Tool))
        {
            return new(WriteStatus.Refused, "prepare_not_allowed");
        }

        WriteSlot slot = _slots.GetOrAdd(owner, static _ => new());
        await slot.Gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (slot.Recovery is not null)
            {
                return new(WriteStatus.Unknown, "outcome_unknown");
            }

            if (slot.Pending is not null)
            {
                await _runner.ResumeAsync(owner, slot.Pending, WriteDecision.Drop, cancellationToken).ConfigureAwait(false);
                slot.Pending = null;
            }

            (WriteResult result, PausedWrite? held) = await _runner.PrepareAsync(owner, request, cancellationToken).ConfigureAwait(false);
            slot.Pending = held;
            return result;
        }
        catch (Exception)
        {
            slot.Pending = null;
            return new(WriteStatus.PrepareFailed, "write_flow_failed");
        }
        finally
        {
            slot.Gate.Release();
        }
    }

    /// <summary>Only exact confirm/yes-apply/cancel reader words are decisions; all other text drops the preview.</summary>
    public async Task<WriteResult> RespondAsync(
        WriteOwner owner, string text, CancellationToken cancellationToken = default)
    {
        ValidateOwner(owner);
        if (!_slots.TryGetValue(owner, out WriteSlot? slot))
        {
            return new(WriteStatus.NothingPending, "nothing_pending");
        }

        await slot.Gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (slot.Recovery is not null)
            {
                return ParseDecision(text) == WriteDecision.Drop
                    ? new(WriteStatus.NothingPending, "recovery_pending")
                    : new(WriteStatus.Unknown, "outcome_unknown");
            }

            PausedWrite? held = slot.Pending;
            slot.Pending = null;
            if (held is null)
            {
                return new(WriteStatus.NothingPending, "nothing_pending");
            }

            WriteDecision decision = ParseDecision(text);
            WriteResult result = await _runner.ResumeAsync(owner, held, decision, cancellationToken).ConfigureAwait(false);
            if (decision == WriteDecision.Confirm && result.Status == WriteStatus.Unknown)
            {
                slot.Recovery = held;
            }

            return result;
        }
        finally
        {
            slot.Gate.Release();
        }
    }

    /// <summary>Looks up the original idempotency identity without dispatching a commit or minting a new key.</summary>
    public async Task<WriteResult> RecoverAsync(WriteOwner owner, CancellationToken cancellationToken = default)
    {
        ValidateOwner(owner);
        if (!_slots.TryGetValue(owner, out WriteSlot? slot))
        {
            return new(WriteStatus.NothingPending, "nothing_pending");
        }

        await slot.Gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (slot.Recovery is not { } held)
            {
                return new(WriteStatus.NothingPending, "nothing_pending");
            }

            WriteResult result = await _runner.ResumeAsync(owner, held, WriteDecision.Recover, cancellationToken).ConfigureAwait(false);
            if (result.Status != WriteStatus.Unknown)
            {
                slot.Recovery = null;
            }

            return result;
        }
        finally
        {
            slot.Gate.Release();
        }
    }

    private static WriteDecision ParseDecision(string text) => text.Trim().ToLowerInvariant().TrimEnd('.', '!').Trim() switch
    {
        "confirm" or "yes, apply" or "yes apply" => WriteDecision.Confirm,
        "cancel" => WriteDecision.Cancel,
        _ => WriteDecision.Drop,
    };

    private static void ValidateOwner(WriteOwner owner)
    {
        ArgumentNullException.ThrowIfNull(owner);
        ArgumentException.ThrowIfNullOrWhiteSpace(owner.PersonId);
        ArgumentException.ThrowIfNullOrWhiteSpace(owner.ConversationId);
    }

}
