using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Infrastructure.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Tests.Artifacts;

public sealed class LocalArtifactByteStoreTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "tcc-artifact-" + Guid.NewGuid().ToString("N"));

    [Theory]
    [InlineData("")]
    [InlineData("nested/file.bin")]
    public async Task Empty_and_binary_bytes_round_trip_at_nested_paths(string suffix)
    {
        var store = new LocalArtifactByteStore(root, "local");
        byte[] bytes = suffix.Length == 0 ? [] : [0, 99, 255, 1];
        string path = suffix.Length == 0 ? "empty.bin" : suffix;
        Assert.Null(await store.GetAsync("outputs", path));
        await store.PutAsync("outputs", path, bytes, "application/octet-stream");
        Assert.Equal(bytes, await store.GetAsync("outputs", path));
        Assert.Null(await store.GetAsync("outputs", path + ".absent"));
    }

    [Fact]
    public async Task Concurrent_publication_has_one_winner_and_never_changes_its_bytes()
    {
        var store = new LocalArtifactByteStore(root, "local");
        var attempts = Enumerable.Range(0, 16).Select(async i =>
        {
            byte[] payload = Enumerable.Repeat((byte)i, 8192).ToArray();
            try
            {
                await store.PutAsync("outputs", "run/package.bin", payload, "application/octet-stream");
                return (Won: true, Payload: payload);
            }
            catch (ArtifactByteException ex) when (ex.Code == "artifact_exists")
            {
                Assert.Equal(409, ex.StatusCode);
                return (Won: false, Payload: payload);
            }
        });
        var results = await Task.WhenAll(attempts);
        var winner = Assert.Single(results.Where(r => r.Won));
        Assert.Equal(winner.Payload, await store.GetAsync("outputs", "run/package.bin"));
        Assert.Empty(Directory.EnumerateFiles(Path.Combine(root, "outputs", "run"), "*.pending"));
    }

    [Theory]
    [InlineData("../escape")]
    [InlineData("/absolute")]
    [InlineData("a/../../escape")]
    [InlineData("a\\..\\escape")]
    [InlineData("C:\\escape")]
    [InlineData("\\\\host\\share\\escape")]
    [InlineData("a//b")]
    [InlineData("./b")]
    [InlineData("a/file:stream")]
    [InlineData("NUL.bin")]
    [InlineData("a/b.")]
    [InlineData("a/b ")]
    public async Task Unsafe_paths_are_refused_for_reads_and_writes(string path)
    {
        var store = new LocalArtifactByteStore(root, "local");
        var write = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            store.PutAsync("outputs", path, new byte[] { 1 }, "t").AsTask());
        var read = await Assert.ThrowsAsync<ArtifactByteException>(() => store.GetAsync("outputs", path).AsTask());
        Assert.Equal("invalid_artifact_path", write.Code);
        Assert.Equal(write.Code, read.Code);
        Assert.False(Directory.Exists(root));
    }

    [Theory]
    [InlineData("../outputs")]
    [InlineData("/outputs")]
    [InlineData("C:outputs")]
    [InlineData("a\\b")]
    public async Task Unsafe_container_is_not_a_file_system_prefix(string container)
    {
        var store = new LocalArtifactByteStore(root, "local");
        await Assert.ThrowsAsync<ArtifactByteException>(() =>
            store.PutAsync(container, "file.bin", new byte[] { 1 }, "t").AsTask());
        Assert.False(Directory.Exists(root));
    }

    [Fact]
    public async Task Cancellation_does_not_publish_or_leave_temporary_bytes()
    {
        var store = new LocalArtifactByteStore(root, "local");
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            store.PutAsync("outputs", "run/file.bin", new byte[] { 1 }, "t", cancellation.Token).AsTask());
        Assert.Null(await store.GetAsync("outputs", "run/file.bin"));
        Assert.Empty(Directory.EnumerateFiles(root, "*.pending", SearchOption.AllDirectories));
    }

    [Fact]
    public async Task Empty_existing_object_is_still_immutable_and_a_directory_is_not_absence()
    {
        var store = new LocalArtifactByteStore(root, "local");
        await store.PutAsync("outputs", "empty.bin", ReadOnlyMemory<byte>.Empty, "t");
        var conflict = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            store.PutAsync("outputs", "empty.bin", new byte[] { 1 }, "t").AsTask());
        Assert.Equal("artifact_exists", conflict.Code);
        Assert.Empty((await store.GetAsync("outputs", "empty.bin"))!);
        Directory.CreateDirectory(Path.Combine(root, "outputs", "directory.bin"));
        var failure = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            store.GetAsync("outputs", "directory.bin").AsTask());
        Assert.Equal("artifact_store_unavailable", failure.Code);
        Assert.DoesNotContain(root, failure.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void Deployed_local_store_fails_at_construction()
    {
        var error = Assert.Throws<ArtifactByteException>(() => new LocalArtifactByteStore(root, "production"));
        Assert.Equal("local_write_refused", error.Code);
        Assert.False(Directory.Exists(root));
    }

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
