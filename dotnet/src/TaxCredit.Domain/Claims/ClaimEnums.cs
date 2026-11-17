namespace TaxCredit.Domain.Claims;

/// <summary>Where a client x program x year sits in the claim lifecycle (Python <c>ClaimStatus</c>, a <c>str, Enum</c>).</summary>
public enum ClaimStatus
{
    /// <summary><c>"not_assessed"</c>.</summary>
    NotAssessed,

    /// <summary><c>"assessed"</c>.</summary>
    Assessed,

    /// <summary><c>"proposed"</c>.</summary>
    Proposed,

    /// <summary><c>"declined"</c>.</summary>
    Declined,

    /// <summary><c>"claimed"</c>.</summary>
    Claimed,

    /// <summary><c>"certified"</c>.</summary>
    Certified,

    /// <summary><c>"amended"</c>.</summary>
    Amended,
}

/// <summary>How we know a figure (Python <c>Provenance</c>).</summary>
public enum Provenance
{
    /// <summary><c>"computed"</c>: our engine identified it.</summary>
    Computed,

    /// <summary><c>"filed_by_us"</c>.</summary>
    FiledByUs,

    /// <summary><c>"client_asserted"</c>: unverified.</summary>
    ClientAsserted,

    /// <summary><c>"inherited"</c>: from a prior provider, unverified.</summary>
    Inherited,

    /// <summary><c>"authority_confirmed"</c>.</summary>
    AuthorityConfirmed,
}

/// <summary>The reading of one coverage cell (Python <c>Outcome</c>).</summary>
public enum Outcome
{
    /// <summary><c>"not_assessed"</c>.</summary>
    NotAssessed,

    /// <summary><c>"correctly_not_claimed"</c>.</summary>
    CorrectlyNotClaimed,

    /// <summary><c>"unclaimed"</c>.</summary>
    Unclaimed,

    /// <summary><c>"confirmed"</c>.</summary>
    Confirmed,

    /// <summary><c>"under_claimed"</c>.</summary>
    UnderClaimed,

    /// <summary><c>"over_claimed"</c>.</summary>
    OverClaimed,

    /// <summary><c>"out_of_scope"</c>.</summary>
    OutOfScope,

    /// <summary><c>"base_year"</c>.</summary>
    BaseYear,
}

/// <summary>Whether we are engaged to handle a program at all (Python <c>EngagementScope</c>).</summary>
public enum EngagementScope
{
    /// <summary><c>"in_scope"</c>.</summary>
    InScope,

    /// <summary><c>"out_of_scope"</c>.</summary>
    OutOfScope,

    /// <summary><c>"prospective"</c>.</summary>
    Prospective,
}

/// <summary>Why you would call a client, in call order (Python <c>PriorityBand</c>).</summary>
public enum PriorityBand
{
    /// <summary><c>"exposed"</c>, rank 0.</summary>
    Exposed,

    /// <summary><c>"on_the_line"</c>, rank 1.</summary>
    OnTheLine,

    /// <summary><c>"declining"</c>, rank 2.</summary>
    Declining,

    /// <summary><c>"unclaimed_at_scale"</c>, rank 3.</summary>
    UnclaimedAtScale,

    /// <summary><c>"not_assessed"</c>, rank 4.</summary>
    NotAssessed,

    /// <summary><c>"settled"</c>, rank 5.</summary>
    Settled,
}
