using System.Text.Json;

namespace TaxCredit.Application.Ports.Contract;

/// <summary>The clock used by run and audit identities; replay never depends on wall time.</summary>
public interface IClock
{
    /// <summary>The current UTC instant.</summary>
    DateTimeOffset UtcNow { get; }
}

/// <summary>Creates identities once at write time, never again on a read.</summary>
public interface IIdSource
{
    /// <summary>Creates a new identity.</summary>
    Guid NewId();
}

/// <summary>Creates opaque confirmation material; deterministic only in the hermetic host.</summary>
public interface ISecretSource
{
    /// <summary>Creates the requested number of bytes.</summary>
    byte[] NextBytes(int count);
}

/// <summary>Minting seam for the replay; token validation belongs to the authentication adapter.</summary>
public interface ITokenMinter
{
    /// <summary>Signs the requested test claims without persisting the token.</summary>
    string Mint(JsonElement specification);
}

/// <summary>Publishes the test public key to an authentication adapter, never a private key.</summary>
public interface IContractSigningKey
{
    /// <summary>The RSA public key in SubjectPublicKeyInfo form.</summary>
    byte[] ExportPublicKey();
}

/// <summary>Persistence and workers replace this seam when their slices are implemented.</summary>
public interface IContractWork
{
    /// <summary>Finishes queued work synchronously before the next replay request.</summary>
    ValueTask<int> Drain(CancellationToken cancellationToken);

    /// <summary>Restores the named profile's seed and clears adapter caches.</summary>
    ValueTask Reset(string profile, CancellationToken cancellationToken);

    /// <summary>Invalidates cached configuration after an environment hook.</summary>
    ValueTask EnvironmentChanged(CancellationToken cancellationToken);
}

/// <summary>Host-local configuration, so one replay cannot mutate another process or host.</summary>
public interface IRuntimeConfiguration
{
    /// <summary>Reads the hook overlay first, then the original host configuration.</summary>
    string? Get(string name);
}
