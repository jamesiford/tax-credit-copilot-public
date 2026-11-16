using TaxCredit.Application.Hosting;

namespace TaxCredit.Api.Hosting;

/// <summary>Replay controls and product requests share one gate, so drain/reset cannot race the next read.</summary>
public sealed class ContractRequestGate(RunWorkGate gate)
{
    /// <summary>Serializes requests only in the hermetic host.</summary>
    public async Task Invoke(HttpContext context, RequestDelegate next)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(next);
        using var lease = await gate.Enter(context.RequestAborted).ConfigureAwait(false);
        await next(context).ConfigureAwait(false);
        await context.Response.CompleteAsync().ConfigureAwait(false);
        await gate.CompleteDeferred(CancellationToken.None).ConfigureAwait(false);
    }
}
