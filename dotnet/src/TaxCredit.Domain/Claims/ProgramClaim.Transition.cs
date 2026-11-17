using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>The optional arguments of <see cref="ProgramClaim.TransitionTo"/> (Python keyword arguments, each <c>None</c> by default).</summary>
public sealed record TransitionOptions
{
    /// <summary>Who made the decision; blank is refused.</summary>
    public string? DecidedBy { get; init; }

    /// <summary>The decline reason; <c>null</c> keeps the old one only when the new status is declined.</summary>
    public string? DeclineReason { get; init; }

    /// <summary><see cref="ClaimMoney.Of"/> input for the claimed amount; <c>null</c> keeps the current one.</summary>
    public object? ClaimedUsd { get; init; }

    /// <summary><see cref="ClaimMoney.Of"/> input for the certified amount; <c>null</c> keeps the current one.</summary>
    public object? CertifiedUsd { get; init; }

    /// <summary>The filing date; <c>null</c> keeps the current one.</summary>
    public DateOnly? FiledOn { get; init; }

    /// <summary>The filing reference; <c>null</c> keeps the current one.</summary>
    public string? FilingReference { get; init; }

    /// <summary>The new provenance; <c>null</c> keeps the current one.</summary>
    public Provenance? Provenance { get; init; }

    /// <summary>The moment of the change; <c>null</c> means "now".</summary>
    public PyDateTime? At { get; init; }
}

/// <summary>The two non-deterministic inputs of a transition (<c>uuid.uuid4()</c> and <c>datetime.now(utc)</c>), injectable so tests are exact.</summary>
/// <param name="NewClaimId">Produces the id of the next record.</param>
/// <param name="Now">Produces the current instant.</param>
public sealed record ClaimClock(Func<string> NewClaimId, Func<PyDateTime> Now)
{
    /// <summary>The real clock and a random GUID.</summary>
    public static ClaimClock System { get; } = new(() => Guid.NewGuid().ToString(), PyDateTime.UtcNow);
}

public sealed partial record ProgramClaim
{
    /// <summary>
    /// Python <c>transition_to(status, **options)</c>: the NEXT record in this cell's history. Does not mutate; raises
    /// <see cref="ClaimError"/> on an illegal move rather than recording a history that could not have happened.
    /// </summary>
    /// <param name="status">The status to move to.</param>
    /// <param name="options">The optional changes.</param>
    /// <param name="clock">The id and time sources; defaults to <see cref="ClaimClock.System"/>.</param>
    /// <returns>The new record, with <c>effective_to</c> open.</returns>
    /// <exception cref="ClaimError">For an illegal move, a blank decider, or (via the constructor) a declined cell without a reason.</exception>
    public ProgramClaim TransitionTo(ClaimStatus status, TransitionOptions options, ClaimClock? clock = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        var env = clock ?? ClaimClock.System;
        var allowed = Status.AllowedTransitions();
        if (!allowed.Contains(status))
        {
            var names = PySort.Sorted(allowed.Select(s => s.Value()), s => s, PyStr.Comparer);
            throw new ClaimError(string.Create(
                CultureInfo.InvariantCulture,
                $"cannot move {ProgramCode} TY{TaxYear} from {Status.Value()} to {status.Value()}. Allowed: {(names.Count > 0 ? string.Join(", ", names) : "none")}."));
        }

        if (PyStr.Strip(options.DecidedBy ?? string.Empty).Length == 0)
        {
            throw new ClaimError("decided_by is required: every status change is somebody's decision");
        }

        var moment = options.At ?? env.Now();
        var newId = env.NewClaimId();
        var claimed = options.ClaimedUsd is not null ? ClaimMoney.Of(options.ClaimedUsd) : ClaimedUsd;
        var certified = options.CertifiedUsd is not null ? ClaimMoney.Of(options.CertifiedUsd) : CertifiedUsd;

        // dataclasses.replace() re-runs __post_init__, so a declined cell without a reason is refused here too.
        return Create(ToSpec() with
        {
            ClaimId = newId,
            Status = status,
            Provenance = options.Provenance ?? Provenance,
            ClaimedUsd = claimed,
            CertifiedUsd = certified,
            FiledOn = options.FiledOn ?? FiledOn,
            FilingReference = options.FilingReference ?? FilingReference,
            DeclineReason = options.DeclineReason ?? (status == ClaimStatus.Declined ? DeclineReason : null),
            DecidedBy = options.DecidedBy,
            DecidedAt = moment,
            EffectiveFrom = moment,
            EffectiveTo = null,
        });
    }
}
