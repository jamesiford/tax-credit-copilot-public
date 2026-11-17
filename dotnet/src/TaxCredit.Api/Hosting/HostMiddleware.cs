using Microsoft.AspNetCore.Routing;
using TaxCredit.Api.Contract;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Api.Hosting;

/// <summary>Unifies transport failures without flattening handled route-family errors.</summary>
public sealed class HostMiddleware(RequestDelegate next, ILogger<HostMiddleware> logger)
{
    private static readonly Action<ILogger, string, Exception?> LogFailure = LoggerMessage.Define<string>(
        LogLevel.Error, new EventId(1, "UnhandledRequest"), "Unhandled request failure ({ExceptionType}).");

    /// <summary>Runs validation and access checks for real endpoints and stubs alike.</summary>
    public async Task InvokeAsync(HttpContext context, RouteTable table, RequestValidator validator, IApiAccess access,
        IApiPrincipalAccessor principals)
    {
        ArgumentNullException.ThrowIfNull(context);
        context.Response.Headers.Vary = "Origin";
        context.Response.OnStarting(() =>
        {
            if (context.Response.ContentType?.StartsWith("application/json", StringComparison.OrdinalIgnoreCase) == true)
            {
                context.Response.ContentType = "application/json";
            }

            return Task.CompletedTask;
        });
        IDisposable? principalScope = null;
        try
        {
            var endpoint = context.GetEndpoint() as RouteEndpoint;
            var operation = endpoint is null ? null : table.Operations.FirstOrDefault(o =>
                string.Equals(o.Path, endpoint.RoutePattern.RawText, StringComparison.OrdinalIgnoreCase)
                && string.Equals(o.Method, context.Request.Method, StringComparison.OrdinalIgnoreCase));
            if (operation is not null)
            {
                var issues = await validator.Validate(context, operation).ConfigureAwait(false);
                if (operation.Group is not ("framework" or "gateway"))
                {
                    var decision = await access.Check(AccessRequest(context), context.RequestAborted).ConfigureAwait(false);
                    if (!decision.Allowed)
                    {
                        if (decision.BearerChallenge)
                        {
                            context.Response.Headers.WWWAuthenticate = "Bearer";
                        }

                        await ApiErrors.Detail(decision.Status, decision.Detail ?? "Not authorized.").ExecuteAsync(context).ConfigureAwait(false);
                        return;
                    }

                    principalScope = principals.Push(decision.Principal ?? ApiPrincipal.Anonymous);
                }
                if (issues.Count > 0)
                {
                    await ApiErrors.Detail(422, issues).ExecuteAsync(context).ConfigureAwait(false);
                    return;
                }
            }

            await next(context).ConfigureAwait(false);
            if (!context.Response.HasStarted && context.Response.StatusCode >= 400 && context.Response.ContentType is null)
            {
                await ApiErrors.Detail(context.Response.StatusCode, context.Response.StatusCode == 404 ? "Not Found" : "Method Not Allowed")
                    .ExecuteAsync(context).ConfigureAwait(false);
            }
        }
        catch (ApiAuthException exception) when (!context.Response.HasStarted)
        {
            await Error(context, exception is AuthDependencyException ? 503 : exception.StatusCode,
                exception.Message, bearer: exception.Challenge is not null && exception is not AuthDependencyException).ConfigureAwait(false);
        }
        catch (RateRefusalException exception) when (!context.Response.HasStarted)
        {
            await Error(context, 429, exception.Decision, retry: exception.Decision.RetryAfterSeconds).ConfigureAwait(false);
        }
        catch (SourceFailureException exception) when (!context.Response.HasStarted)
        {
            object body = exception is SourceFootprintUnavailable footprint
                ? new { code = exception.Code, dependency = exception.Dependency, remedy = exception.Remedy, reason = footprint.Reason, impact = footprint.Impact }
                : new { code = exception.Code, dependency = exception.Dependency, remedy = exception.Remedy };
            await Error(context, exception is SourceTooLarge ? 422 : 503, body).ConfigureAwait(false);
        }
        catch (ArtifactByteException exception) when (!context.Response.HasStarted)
        {
            await Error(context, exception.StatusCode, exception.Message).ConfigureAwait(false);
        }
        catch (RefusedException exception) when (!context.Response.HasStarted)
        {
            await Error(context, 403, exception.Message).ConfigureAwait(false);
        }
        catch (ValidationFailedException exception) when (!context.Response.HasStarted)
        {
            await Error(context, 422, exception.Failures).ConfigureAwait(false);
        }
        catch (BadHttpRequestException exception) when (!context.Response.HasStarted)
        {
            await Error(context, exception.StatusCode, "Invalid HTTP request.").ConfigureAwait(false);
        }
#pragma warning disable CA1031 // This boundary deliberately translates all unhandled failures to JSON without private data or stacks.
        catch (Exception exception) when (!context.Response.HasStarted)
        {
            LogFailure(logger, exception.GetType().Name, null);
            await Error(context, 500, "Internal Server Error").ConfigureAwait(false);
        }
#pragma warning restore CA1031
        finally
        {
            principalScope?.Dispose();
        }
    }

    private static Task Error(HttpContext context, int status, object detail, bool bearer = false, int? retry = null)
    {
        context.Response.Clear();
        context.Response.Headers.Vary = "Origin";
        if (bearer) { context.Response.Headers.WWWAuthenticate = "Bearer"; }
        if (retry is not null) { context.Response.Headers.RetryAfter = retry.Value.ToString(System.Globalization.CultureInfo.InvariantCulture); }
        return ApiErrors.Detail(status, detail).ExecuteAsync(context);
    }

    private static ApiAccessRequest AccessRequest(HttpContext context) => new(
        context.Request.Method, context.Request.Path.Value ?? "",
        context.Request.Headers.ToDictionary(h => h.Key, h => h.Value.ToString(), StringComparer.OrdinalIgnoreCase),
        context.Request.RouteValues.ToDictionary(v => v.Key, v => Convert.ToString(v.Value, System.Globalization.CultureInfo.InvariantCulture) ?? "", StringComparer.Ordinal),
        context.Request.Query.ToDictionary(q => q.Key, q => (IReadOnlyList<string>)q.Value.Select(v => v ?? "").ToArray(), StringComparer.Ordinal),
        RequestValidator.Body(context));
}
