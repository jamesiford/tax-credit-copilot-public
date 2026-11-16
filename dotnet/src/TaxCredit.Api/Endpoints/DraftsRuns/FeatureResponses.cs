using System.Globalization;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

internal static class FeatureResponses
{
    internal static async Task<IResult> Send(IMediator mediator, IRequest<object> request, CancellationToken cancellationToken, int status = 200, HttpContext? context = null)
    {
        try
        {
            var result = await mediator.Send(request, cancellationToken).ConfigureAwait(false);
            if (result is DraftDownload download && context is not null)
            {
                context.Response.Headers["X-Bundle-Sha256"] = download.Sha256;
                context.Response.Headers["X-Verification"] = "not_verified";
                context.Response.Headers["X-Wrote-Local-Files"] = "0";
                return Results.File(download.Bytes, "application/zip", download.FileName);
            }
            return Results.Json(FeatureValues.Wire(result), statusCode: status);
        }
        catch (DraftsRunsRefusalException refused) { return ApiErrors.Detail(refused.Status, refused.Detail); }
        catch (DraftError refused)
        {
            return ApiErrors.Detail(refused is DraftNotFound ? 404 : refused is DraftConflict or InvalidTransition ? 409 :
                refused is CustomerDataRefused ? 403 : 422, new { code = refused.Code, reason = refused.Message });
        }
        catch (ClientRunNotAvailable refused) { return ApiErrors.Detail(404, refused.Message); }
        catch (PyValueError refused) { return ApiErrors.Detail(422, refused.Message); }
        catch (ProgramNotRunnable refused) { return ApiErrors.Detail(422, refused.Message); }
        catch (ProgramStateConflict refused) { return ApiErrors.Detail(422, refused.Message); }
        catch (OverflowException) { return ApiErrors.Detail(422, "A request quantity is outside the supported range."); }
    }

    internal static string? Query(HttpContext context, string name) =>
        context.Request.Query.TryGetValue(name, out var values) ? values.Last() : null;
    internal static long Number(HttpContext context, string name, long fallback) =>
        Query(context, name) is { } text ? long.Parse(text, CultureInfo.InvariantCulture) : fallback;
    internal static string Route(HttpContext context, string name) => (string)context.Request.RouteValues[name]!;
}
