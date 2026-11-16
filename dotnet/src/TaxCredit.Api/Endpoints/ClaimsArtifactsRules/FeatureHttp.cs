using System.Globalization;
using System.Text.Json;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Api.Endpoints.ClaimsArtifactsRules;

internal static class FeatureHttp
{
    internal static string? Query(HttpContext context, string name, string? fallback = null) =>
        context.Request.Query.TryGetValue(name, out var value) ? value.LastOrDefault() : fallback;
    internal static long? Year(HttpContext context, string name) =>
        Query(context, name) is { } text ? long.Parse(text, CultureInfo.InvariantCulture) : null;
    internal static long Client(HttpContext context) => PathInteger(context, "client_id");
    internal static long PathInteger(HttpContext context, string name) =>
        long.TryParse(Path(context, name), CultureInfo.InvariantCulture, out var value)
            ? value : throw new FeatureRefusalException(422, $"invalid {name}");
    internal static string Path(HttpContext context, string name) => (string)context.Request.RouteValues[name]!;
    internal static JsonElement Body(HttpContext context) => RequestValidator.Body(context)!.Value;
    internal static ApiPrincipal Principal(HttpContext context) =>
        context.RequestServices.GetRequiredService<IApiPrincipalAccessor>().Current ?? ApiPrincipal.Anonymous;
    internal static string Actor(HttpContext context, string? supplied = null, string fallback = "system") =>
        Principal(context).Attributed(supplied, fallback);

    internal static async Task<IResult> Send<T>(HttpContext context, Func<IRequest<T>> request, int status = 200)
    {
        try
        {
            var response = await context.RequestServices.GetRequiredService<IMediator>()
                .Send(request(), context.RequestAborted).ConfigureAwait(false);
            return Results.Json(FeatureValues.Wire(response), statusCode: status);
        }
        catch (FeatureRefusalException refusal) { return ApiErrors.Detail(refusal.Status, refusal.Detail); }
        catch (ClaimError error) { return ApiErrors.Detail(422, error.Message); }
        catch (PyInvalidOperation) { return ApiErrors.Detail(422, "invalid decimal amount"); }
        catch (PyValueError error) { return ApiErrors.Detail(422, error.Message); }
        catch (OverflowException) { return ApiErrors.Detail(422, "value is outside the supported range"); }
    }
}
