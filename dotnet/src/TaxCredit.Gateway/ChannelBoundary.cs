using TaxCredit.Gateway.Execution;

namespace TaxCredit.Gateway;

internal sealed class ChannelBoundary(RequestDelegate next, ILogger<ChannelBoundary> logger)
{
    private static readonly Action<ILogger, Exception?> Failed = LoggerMessage.Define(LogLevel.Error,
        new EventId(20, "ChannelFailure"), "The channel request failed unexpectedly.");

    public async Task InvokeAsync(HttpContext context)
    {
        if (!context.Request.Path.StartsWithSegments("/channel") && context.Request.Path != "/mcp")
        { await next(context).ConfigureAwait(false); return; }
        try
        {
            await next(context).ConfigureAwait(false);
        }
        catch (ChannelFailure failure) when (!context.Response.HasStarted)
        {
            if (failure.Status == 401) { context.Response.Headers.WWWAuthenticate = "Bearer"; }
            await ChannelEndpoints.Json(failure.Status, failure.Body(context.Items["channel-correlation"] as string)).ExecuteAsync(context).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested)
        { context.Abort(); }
#pragma warning disable CA1031 // HTTP boundary returns a safe channel error; no exception text or request payload is logged.
        catch (Exception) when (!context.Response.HasStarted)
        {
            Failed(logger, null);
            await ChannelEndpoints.Json(500, new ChannelFailure(500, "internal_error", "The gateway failed unexpectedly.", true).Body())
                .ExecuteAsync(context).ConfigureAwait(false);
        }
#pragma warning restore CA1031
    }
}
