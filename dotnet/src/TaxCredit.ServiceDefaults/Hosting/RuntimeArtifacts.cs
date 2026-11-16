using Azure.Identity;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Infrastructure.Ai.Artifacts;

namespace TaxCredit.ServiceDefaults.Hosting;

internal static class RuntimeArtifactRegistration
{
    internal static void AddRuntimeArtifacts(this IServiceCollection services, RuntimeConfiguration settings, RuntimePaths paths, bool hooks)
    {
        if (settings.Get("ARTIFACT_STORE") == "blob")
        {
            services.AddBlobArtifactBytes(new Uri(RuntimeRegistration.Required(settings, "ARTIFACT_BLOB_ACCOUNT_URL")), new DefaultAzureCredential());
        }
        else if (settings.Get("ARTIFACT_STORE") == "local")
        {
            var environment = RuntimeRegistration.Required(settings, "ENVIRONMENT");
            services.AddLocalArtifactBytes(paths.Artifacts, environment);
            if (hooks)
            {
                services.AddSingleton(new ArtifactGenerations(paths.Artifacts, environment));
                services.AddScoped<IArtifactByteStore>(p => p.GetRequiredService<ArtifactGenerations>().Acquire());
            }
        }
        else
        {
            throw new InvalidOperationException("Unknown ARTIFACT_STORE.");
        }
    }
}

/// <summary>Reset owns only its private generation; a normal local or deployed byte root is never cleaned.</summary>
public sealed class ArtifactGenerations : IDisposable
{
    private readonly string _parent;
    private readonly string _environment;
    private readonly object _gate = new();
    private IArtifactByteStore _current;
    private int _users;
    private string _generation = "";

    /// <summary>Exclusive random generation names are internal paths, not public identities or calculation facts.</summary>
    public ArtifactGenerations(string parent, string environment)
    {
        _parent = Path.GetFullPath(parent);
        _environment = environment;
        _current = Create();
    }

    /// <summary>The request scope pins a store; callers exclude all readers before rotating.</summary>
    public IArtifactByteStore Acquire()
    {
        lock (_gate) { _users++; return new GenerationLease(this, _current); }
    }

    /// <summary>No active consumer may survive this operation.</summary>
    public void Reset()
    {
        lock (_gate) { WaitForUsers(); Clean(); _current = Create(); }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        lock (_gate) { WaitForUsers(); Clean(); }
    }

    private void WaitForUsers()
    {
        var deadline = System.Diagnostics.Stopwatch.StartNew();
        while (_users != 0)
        {
            if (deadline.Elapsed >= TimeSpan.FromSeconds(5)) { throw new InvalidOperationException("Artifact users must dispose before reset."); }
            Monitor.Wait(_gate, TimeSpan.FromMilliseconds(50));
        }
    }

    private void Release()
    {
        lock (_gate) { _users--; Monitor.PulseAll(_gate); }
    }

    private sealed class GenerationLease(ArtifactGenerations owner, IArtifactByteStore store) : IArtifactByteStore, IDisposable
    {
        private int _disposed;
        public bool IsDurable => store.IsDurable;
        public ValueTask PutAsync(string container, string path, ReadOnlyMemory<byte> bytes, string contentType,
            CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(_disposed != 0, this);
            return store.PutAsync(container, path, bytes, contentType, cancellationToken);
        }
        public ValueTask<byte[]?> GetAsync(string container, string path, CancellationToken cancellationToken = default)
        {
            ObjectDisposedException.ThrowIf(_disposed != 0, this);
            return store.GetAsync(container, path, cancellationToken);
        }
        public void Dispose() { if (Interlocked.Exchange(ref _disposed, 1) == 0) { owner.Release(); } }
    }

    private LocalArtifactByteStore Create()
    {
        var path = Path.Combine(_parent, "replay-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        using (new FileStream(Path.Combine(path, ".owned"), FileMode.CreateNew, FileAccess.Write, FileShare.None)) { }
        _generation = path;
        return new LocalArtifactByteStore(path, _environment);
    }

    private void Clean()
    {
        if (_generation.Length == 0) { return; }
        if (!File.Exists(Path.Combine(_generation, ".owned"))
            || (File.GetAttributes(_generation) & FileAttributes.ReparsePoint) != 0
            || Directory.EnumerateFileSystemEntries(_generation, "*", SearchOption.AllDirectories)
                .Any(p => (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0))
        {
            throw new IOException("Artifact generation ownership or link safety check failed.");
        }

        Directory.Delete(_generation, recursive: true);
        _generation = "";
    }
}
