namespace TaxCredit.Api.Hosting;

/// <summary>Replay controls and product requests share one gate, so drain/reset cannot race the next read.</summary>
public sealed class ContractRequestGate : IDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);

    /// <summary>Serializes requests only in the hermetic host.</summary>
    public async Task Invoke(HttpContext context, RequestDelegate next)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(next);
        await _gate.WaitAsync(context.RequestAborted).ConfigureAwait(false);
        try
        {
            await next(context).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <inheritdoc />
    public void Dispose() => _gate.Dispose();
}
