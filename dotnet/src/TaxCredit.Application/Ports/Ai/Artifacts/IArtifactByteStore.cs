namespace TaxCredit.Application.Ports.Ai.Artifacts;

/// <summary>Immutable artifact bytes; metadata, visibility and access auditing are separate ports.</summary>
public interface IArtifactByteStore
{
    /// <summary>Whether the backing store is suitable as the deployed system of record.</summary>
    bool IsDurable { get; }

    /// <summary>Publishes complete bytes at a new logical path; existing paths must never be overwritten.</summary>
    ValueTask PutAsync(string container, string path, ReadOnlyMemory<byte> bytes, string contentType,
        CancellationToken cancellationToken = default);

    /// <summary>Returns stored bytes, or null only if the object is absent.</summary>
    ValueTask<byte[]?> GetAsync(string container, string path, CancellationToken cancellationToken = default);
}

/// <summary>Safe error vocabulary for host mapping; transport and file-system details are not exposed.</summary>
public sealed class ArtifactByteException : Exception
{
    /// <summary>Creates an artifact error with a stable application code and suggested HTTP status.</summary>
    public ArtifactByteException(string code, int statusCode, string reason) : base(reason)
    {
        Code = code;
        StatusCode = statusCode;
    }

    /// <summary>Stable machine-readable reason.</summary>
    public string Code { get; }

    /// <summary>Suggested status; the host owns the detail-family response.</summary>
    public int StatusCode { get; }
}
