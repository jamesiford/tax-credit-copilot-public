using Azure;
using Azure.Identity;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using TaxCredit.Application.Ports.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Artifacts;

/// <summary>Private Blob storage through an injectable SDK client; no browser URL or SAS is exposed.</summary>
public sealed class BlobArtifactByteStore(BlobServiceClient client) : IArtifactByteStore
{
    private readonly BlobServiceClient client = client ?? throw new ArgumentNullException(nameof(client));

    /// <inheritdoc/>
    public bool IsDurable => true;

    /// <inheritdoc/>
    public async ValueTask PutAsync(string container, string path, ReadOnlyMemory<byte> bytes, string contentType,
        CancellationToken cancellationToken = default)
    {
        ArtifactPaths.Validate(container, path);
        ArgumentException.ThrowIfNullOrWhiteSpace(contentType);
        try
        {
            await client.GetBlobContainerClient(container).GetBlobClient(path).UploadAsync(
                BinaryData.FromBytes(bytes), new BlobUploadOptions
                {
                    HttpHeaders = new BlobHttpHeaders { ContentType = contentType },
                    Conditions = new BlobRequestConditions { IfNoneMatch = ETag.All }
                }, cancellationToken).ConfigureAwait(false);
        }
        catch (RequestFailedException ex) when (ex.Status is 409 or 412 &&
            ex.ErrorCode is "BlobAlreadyExists" or "ConditionNotMet")
        {
            throw ArtifactPaths.Conflict();
        }
        catch (Exception ex) when (ex is RequestFailedException or HttpRequestException or AuthenticationFailedException)
        {
            throw ArtifactPaths.Unavailable();
        }
    }

    /// <inheritdoc/>
    public async ValueTask<byte[]?> GetAsync(string container, string path, CancellationToken cancellationToken = default)
    {
        ArtifactPaths.Validate(container, path);
        try
        {
            var response = await client.GetBlobContainerClient(container).GetBlobClient(path)
                .DownloadContentAsync(cancellationToken).ConfigureAwait(false);
            return response.Value.Content.ToArray();
        }
        catch (RequestFailedException ex) when (ex.Status == 404 && ex.ErrorCode == "BlobNotFound")
        {
            return null;
        }
        catch (Exception ex) when (ex is RequestFailedException or HttpRequestException or AuthenticationFailedException)
        {
            throw ArtifactPaths.Unavailable();
        }
    }
}
