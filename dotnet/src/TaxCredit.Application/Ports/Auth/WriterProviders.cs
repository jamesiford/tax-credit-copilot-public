namespace TaxCredit.Application.Ports.Auth;

/// <summary>Group membership I/O can be replaced without granting rights on provider failure.</summary>
public interface IGroupMembershipProvider
{
    /// <summary>Only a successful explicit member/nonmember answer may be cached.</summary>
    ValueTask<bool> IsMemberAsync(string userOid, string groupId, CancellationToken cancellationToken = default);
}

/// <summary>The host supplies managed-identity credentials; secrets never enter this contract.</summary>
public interface IAuthAccessTokenProvider
{
    /// <summary>Acquire a token for a fixed configured resource scope.</summary>
    ValueTask<string> GetTokenAsync(string scope, CancellationToken cancellationToken = default);
    /// <summary>A permission refresh invalidates only this credential's token; false refuses a redundant refresh.</summary>
    bool Invalidate(string scope);
}
