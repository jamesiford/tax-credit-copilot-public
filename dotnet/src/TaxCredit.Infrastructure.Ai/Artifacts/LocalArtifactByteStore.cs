using TaxCredit.Application.Ports.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Artifacts;

/// <summary>Development-only, create-only publication without exposing incomplete final objects.</summary>
public sealed class LocalArtifactByteStore : IArtifactByteStore
{
    private readonly string root;

    /// <summary>Requires explicit local deployment; callers must exclusively control the storage directory.</summary>
    public LocalArtifactByteStore(string root, string environment)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(root);
        if (!string.Equals(environment, "local", StringComparison.Ordinal))
        {
            throw new ArtifactByteException("local_write_refused", 503,
                "Local artifact storage is not durable and cannot be used in a deployed environment.");
        }
        this.root = Path.GetFullPath(root);
    }

    /// <inheritdoc/>
    public bool IsDurable => false;

    /// <inheritdoc/>
    public async ValueTask PutAsync(string container, string path, ReadOnlyMemory<byte> bytes, string contentType,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(contentType);
        string target = Resolve(container, path);
        string parent = Path.GetDirectoryName(target)!;
        string temporary = Path.Combine(parent, "." + Guid.NewGuid().ToString("N") + ".pending");
        bool temporaryCreated = false;
        try
        {
            EnsureNoLinks(parent);
            Directory.CreateDirectory(parent);
            EnsureNoLinks(parent);
            await using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write,
                FileShare.None, 4096, FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                temporaryCreated = true;
                await stream.WriteAsync(bytes, cancellationToken).ConfigureAwait(false);
                await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
            }
            cancellationToken.ThrowIfCancellationRequested();
            EnsureNoLinks(parent);
            File.Move(temporary, target, overwrite: false);
        }
        catch (IOException) when (File.Exists(target) || Directory.Exists(target))
        {
            throw ArtifactPaths.Conflict();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw ArtifactPaths.Unavailable();
        }
        finally
        {
            if (temporaryCreated)
            {
                DeletePending(temporary);
            }
        }
    }

    /// <inheritdoc/>
    public async ValueTask<byte[]?> GetAsync(string container, string path, CancellationToken cancellationToken = default)
    {
        string target = Resolve(container, path);
        try
        {
            EnsureNoLinks(target);
            return await File.ReadAllBytesAsync(target, cancellationToken).ConfigureAwait(false);
        }
        catch (FileNotFoundException)
        {
            return null;
        }
        catch (DirectoryNotFoundException)
        {
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw ArtifactPaths.Unavailable();
        }
    }

    private string Resolve(string container, string path)
    {
        string[] parts = ArtifactPaths.Validate(container, path);
        return Path.Combine([root, container, .. parts]);
    }

    private static void EnsureNoLinks(string path)
    {
        for (string? candidate = path; candidate is not null; candidate = Path.GetDirectoryName(candidate))
        {
            FileAttributes attributes;
            try
            {
                attributes = File.GetAttributes(candidate);
            }
            catch (FileNotFoundException)
            {
                continue;
            }
            catch (DirectoryNotFoundException)
            {
                continue;
            }
            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw ArtifactPaths.InvalidPath();
            }
        }
    }

    private static void DeletePending(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw ArtifactPaths.Unavailable();
        }
    }
}
