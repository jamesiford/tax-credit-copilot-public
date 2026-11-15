namespace TaxCredit.Api.Wire;

/// <summary>The error families consumed by the portal; never ASP.NET ProblemDetails.</summary>
public static class ApiErrors
{
    /// <summary>A handled string or structured-detail error.</summary>
    public static IResult Detail(int status, object detail) => Results.Json(new { detail }, statusCode: status);

    /// <summary>A dependency failure has its own top-level family.</summary>
    public static IResult Dependency(string dependency, string reason, string remedy) =>
        Results.Json(new { detail = $"{dependency} unavailable: {reason} {remedy}", dependency, reason, remedy }, statusCode: StatusCodes.Status503ServiceUnavailable);

    /// <summary>The run-batch family deliberately nests its detail.</summary>
    public static IResult RunBatch(int status, string code, string detail) => Detail(status, new { detail, code });
}
