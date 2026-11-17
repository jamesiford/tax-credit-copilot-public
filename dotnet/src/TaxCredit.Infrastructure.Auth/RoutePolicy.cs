using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Metadata obligations for endpoint owners; this class does not register routes or bypass policies.</summary>
public static class RoutePolicy
{
    private static readonly Regex[] Forbidden = [
        Pattern(@"^POST /api/ingestion/\d+/exceptions/[^/]+/resolve$"),
        Pattern(@"^POST /api/onezero/employee/[^/]+/review$"),
        Pattern(@"^POST /api/rules/[^/]+/verify$"),
        Pattern(@"^POST /api/rules/ingested/[^/]+/apply$"),
        Pattern(@"^POST /api/workspace/(refresh|comparison/stage)$"),
        Pattern(@"^POST /api/v2/clients/\d+/runs$"),
        Pattern(@"^POST /api/claims/assess$"),
        Pattern(@"^POST /api/v2/run-batches(/[^/]+/(cancel|retry-failed))?$"),
        Pattern(@"^(POST|PUT) /api/v2/program-drafts(/[^/]+/(documents|validate|request-review|review|withdraw|preview|export))?$")
    ];
    private static readonly Regex SelfAuthorizing = Pattern(@"^/api/clients/\d+/artifacts/[^/]+$");

    /// <summary>Framework documentation endpoints are outside the Python guard.</summary>
    public static bool IsPublic(string path) => path is "/api/health" or "/api/ready" or "/docs" or "/docs/oauth2-redirect" or "/redoc" or "/openapi.json";
    /// <summary>Requires acting-user binding first, not an impersonated author.</summary>
    public static bool IsAgentForbidden(string method, string path) => Forbidden.Any(p => p.IsMatch($"{method.ToUpperInvariant()} {path}"));
    /// <summary>Artifacts look up existence, record denied access and authorize within their handler.</summary>
    public static bool IsSelfAuthorizing(string path) => SelfAuthorizing.IsMatch(path);
    /// <summary>Audit handlers must refuse service-principal reads, even if the acting person is a writer.</summary>
    public static bool IsPersonOnlyRead(string method, string path) =>
        method.Equals("GET", StringComparison.OrdinalIgnoreCase) && path == "/api/audit/channel";
    /// <summary>F-15's recorded 403 needs an explicit owner decision; never manufacture a query actor to pass writer checks.</summary>
    public static bool RequiresAgentReadReview(string method, string path) =>
        method.Equals("GET", StringComparison.OrdinalIgnoreCase) && path == "/api/v2/program-drafts";
    /// <summary>Every write requires an explicit policy decision; F-14 exceptions need W2 owner review.</summary>
    public static bool RequiresWriterDecision(string method) => method.ToUpperInvariant() is "POST" or "PUT" or "PATCH" or "DELETE";
    /// <summary>F-14 cases must not silently turn previously valid allowed writes into refusals.</summary>
    public static IReadOnlyList<string> WriterReviewCases { get; } = Array.AsReadOnly(new[]
    {
        "p1_auth:reader.assess", "p1_auth:reader.run", "p1_auth:reader.rules-verify", "p1_auth:reader.batch-dry-run"
    });
    /// <summary>Only these API kinds are rate-limited; the API default is 60, not the gateway's 6.</summary>
    public static string? RateLimitKind(string method, string path)
    {
        var route = $"{method.ToUpperInvariant()} {path}";
        if (route == "POST /api/v2/run-batches")
        {
            return "batch_start";
        }

        if (Pattern(@"^PUT /api/v2/program-drafts/[^/]+/documents$").IsMatch(route))
        {
            return "draft_save";
        }

        if (Pattern(@"^POST /api/v2/program-drafts/[^/]+/preview$").IsMatch(route))
        {
            return "draft_preview";
        }

        if (Pattern(@"^POST /api/v2/program-drafts/[^/]+/export$").IsMatch(route))
        {
            return "draft_export";
        }

        return null;
    }
    private static Regex Pattern(string value) => new(value, RegexOptions.CultureInvariant | RegexOptions.NonBacktracking, TimeSpan.FromMilliseconds(100));
}
