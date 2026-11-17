namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Bounded host-local serialization closes the in-flight result gap between scoped callers.</summary>
internal sealed class CapabilityCommitLocks
{
    private readonly SemaphoreSlim[] _stripes = Enumerable.Range(0, 256).Select(_ => new SemaphoreSlim(1, 1)).ToArray();

    internal async Task<IDisposable> EnterAsync(string person, string key, CancellationToken cancellationToken)
    {
        var index = (int)((uint)HashCode.Combine(person, key) % (uint)_stripes.Length);
        var stripe = _stripes[index];
        await stripe.WaitAsync(cancellationToken).ConfigureAwait(false);
        return new Lease(stripe);
    }

    private sealed class Lease(SemaphoreSlim semaphore) : IDisposable
    {
        public void Dispose() => semaphore.Release();
    }
}
