using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>The string values, predicates and tables Python attaches to the claim enums.</summary>
public static class ClaimEnumExtensions
{
    private static readonly (ClaimStatus Status, string Value)[] Statuses =
    [
        (ClaimStatus.NotAssessed, "not_assessed"), (ClaimStatus.Assessed, "assessed"), (ClaimStatus.Proposed, "proposed"),
        (ClaimStatus.Declined, "declined"), (ClaimStatus.Claimed, "claimed"), (ClaimStatus.Certified, "certified"), (ClaimStatus.Amended, "amended"),
    ];

    private static readonly (Provenance Provenance, string Value)[] Provenances =
    [
        (Provenance.Computed, "computed"), (Provenance.FiledByUs, "filed_by_us"), (Provenance.ClientAsserted, "client_asserted"),
        (Provenance.Inherited, "inherited"), (Provenance.AuthorityConfirmed, "authority_confirmed"),
    ];

    private static readonly (Outcome Outcome, string Value)[] Outcomes =
    [
        (Outcome.NotAssessed, "not_assessed"), (Outcome.CorrectlyNotClaimed, "correctly_not_claimed"), (Outcome.Unclaimed, "unclaimed"),
        (Outcome.Confirmed, "confirmed"), (Outcome.UnderClaimed, "under_claimed"), (Outcome.OverClaimed, "over_claimed"),
        (Outcome.OutOfScope, "out_of_scope"), (Outcome.BaseYear, "base_year"),
    ];

    private static readonly (EngagementScope Scope, string Value)[] Scopes =
    [
        (EngagementScope.InScope, "in_scope"), (EngagementScope.OutOfScope, "out_of_scope"), (EngagementScope.Prospective, "prospective"),
    ];

    private static readonly (PriorityBand Band, string Value)[] Bands =
    [
        (PriorityBand.Exposed, "exposed"), (PriorityBand.OnTheLine, "on_the_line"), (PriorityBand.Declining, "declining"),
        (PriorityBand.UnclaimedAtScale, "unclaimed_at_scale"), (PriorityBand.NotAssessed, "not_assessed"), (PriorityBand.Settled, "settled"),
    ];

    /// <summary>Python <c>status.value</c>.</summary>
    /// <param name="status">The status.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this ClaimStatus status) => Statuses.First(s => s.Status == status).Value;

    /// <summary>Python <c>ClaimStatus(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The status.</returns>
    /// <exception cref="PyValueError">For a value that is not a member.</exception>
    public static ClaimStatus StatusFromValue(string value) =>
        Statuses.FirstOrDefault(s => s.Value == value) is { Value: not null } hit ? hit.Status : throw new PyValueError($"'{value}' is not a valid ClaimStatus");

    /// <summary>Python <c>status.is_claimed</c>: has money actually been claimed against this cell?</summary>
    /// <param name="status">The status.</param>
    /// <returns><c>true</c> for claimed, certified and amended.</returns>
    public static bool IsClaimed(this ClaimStatus status) => status is ClaimStatus.Claimed or ClaimStatus.Certified or ClaimStatus.Amended;

    /// <summary>Python <c>_ALLOWED_TRANSITIONS[status]</c>: the legal next statuses.</summary>
    /// <remarks>Why a table: a lifecycle that permits anything is not a lifecycle (<c>domain/claims.py</c>).</remarks>
    /// <param name="status">The current status.</param>
    /// <returns>The statuses it may move to.</returns>
    public static IReadOnlyList<ClaimStatus> AllowedTransitions(this ClaimStatus status) => status switch
    {
        ClaimStatus.NotAssessed => [ClaimStatus.Assessed],
        ClaimStatus.Assessed => [ClaimStatus.Proposed, ClaimStatus.Assessed, ClaimStatus.Declined],
        ClaimStatus.Proposed => [ClaimStatus.Claimed, ClaimStatus.Declined, ClaimStatus.Assessed],
        ClaimStatus.Declined => [ClaimStatus.Proposed, ClaimStatus.Assessed],
        ClaimStatus.Claimed => [ClaimStatus.Certified, ClaimStatus.Amended],
        ClaimStatus.Certified => [ClaimStatus.Amended],
        _ => [ClaimStatus.Certified, ClaimStatus.Amended],
    };

    /// <summary>Python <c>provenance.value</c>.</summary>
    /// <param name="provenance">The provenance.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this Provenance provenance) => Provenances.First(s => s.Provenance == provenance).Value;

    /// <summary>Python <c>Provenance(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The provenance.</returns>
    public static Provenance ProvenanceFromValue(string value) => Provenances.First(s => s.Value == value).Provenance;

    /// <summary>Python <c>provenance.verified</c>: false for anything resting only on somebody's word.</summary>
    /// <param name="provenance">The provenance.</param>
    /// <returns><c>true</c> for computed, filed by us and authority confirmed.</returns>
    public static bool Verified(this Provenance provenance) =>
        provenance is Provenance.Computed or Provenance.FiledByUs or Provenance.AuthorityConfirmed;

    /// <summary>Python <c>outcome.value</c>.</summary>
    /// <param name="outcome">The outcome.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this Outcome outcome) => Outcomes.First(s => s.Outcome == outcome).Value;

    /// <summary>Python <c>EngagementScope.value</c>.</summary>
    /// <param name="scope">The scope.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this EngagementScope scope) => Scopes.First(s => s.Scope == scope).Value;

    /// <summary>Python <c>EngagementScope(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The scope.</returns>
    public static EngagementScope ScopeFromValue(string value) => Scopes.First(s => s.Value == value).Scope;

    /// <summary>Python <c>band.value</c>.</summary>
    /// <param name="band">The band.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this PriorityBand band) => Bands.First(s => s.Band == band).Value;

    /// <summary>Python <c>band.rank</c>: descending call order, lower sorts first.</summary>
    /// <param name="band">The band.</param>
    /// <returns>0 for exposed through 5 for settled.</returns>
    public static long Rank(this PriorityBand band) => band switch
    {
        PriorityBand.Exposed => 0,
        PriorityBand.OnTheLine => 1,
        PriorityBand.Declining => 2,
        PriorityBand.UnclaimedAtScale => 3,
        PriorityBand.NotAssessed => 4,
        _ => 5,
    };
}
