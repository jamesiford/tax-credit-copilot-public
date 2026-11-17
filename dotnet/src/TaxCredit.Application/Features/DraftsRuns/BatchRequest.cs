using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;
using static TaxCredit.Application.Features.DraftsRuns.FeatureValues;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Normalized selection and execution intent; a preview and an accepted request use the same plan.</summary>
public sealed record BatchRequest
{
    /// <summary>The operation performed for each selected client.</summary>
    public BatchKind Kind { get; init; }
    /// <summary>The way clients are selected.</summary>
    public ScopeKind Scope { get; init; }
    /// <summary>Named clients, with request order retained.</summary>
    public IReadOnlyList<long> Clients { get; init; } = [];
    /// <summary>Portfolio predicates.</summary>
    public PyDict Filter { get; init; } = new();
    /// <summary>Explicit program, or programs derived from footprint.</summary>
    public string? ProgramCode { get; init; }
    /// <summary>Requested year order survives storage.</summary>
    public IReadOnlyList<long> TaxYears { get; init; } = [];
    /// <summary>Forces calculation even with matching evidence.</summary>
    public bool Force { get; init; }
    /// <summary>Skipping is opt-in and decided at execution time.</summary>
    public bool SkipUnchanged { get; init; }
    /// <summary>Includes the build identity in unchanged comparisons.</summary>
    public bool IncludeCodeCommit { get; init; }
    /// <summary>Defaults to one replay for all authored years.</summary>
    public bool RefreshOnce { get; init; } = true;
    /// <summary>The requester's replay key.</summary>
    public string? IdempotencyKey { get; init; }
    /// <summary>Allows a deliberately confirmed whole-book request above the normal ceiling.</summary>
    public bool OverrideSizeLimit { get; init; }
    /// <summary>Typed confirmation of the planned item count.</summary>
    public long? ConfirmItems { get; init; }

    /// <summary>Parses fields after schema validation and applies cross-field rules for non-HTTP callers too.</summary>
    public static BatchRequest Parse(PyDict body)
    {
        var scope = Map(body, "scope");
        var request = new BatchRequest
        {
            Kind = RunEnumExtensions.BatchKindFromValue(Text(body, "kind", "calculate")!),
            Scope = RunEnumExtensions.ScopeKindFromValue(Text(scope, "kind", "list")!),
            Clients = Years(scope, "client_ids").Distinct().ToArray(),
            Filter = Map(scope, "filter"),
            ProgramCode = Text(body, "program_code"),
            TaxYears = Years(body, "tax_years"),
            Force = Flag(body, "force"),
            SkipUnchanged = Flag(body, "skip_unchanged"),
            IncludeCodeCommit = Flag(body, "include_code_commit"),
            RefreshOnce = Flag(body, "refresh_once", true),
            IdempotencyKey = Text(body, "idempotency_key"),
            OverrideSizeLimit = Flag(body, "override_size_limit"),
            ConfirmItems = body.TryGetValue("confirm_items", out var confirm) && confirm is not null ? Integer(body, "confirm_items") : null,
        };
        request.Validate();
        return request;
    }

    private void Validate()
    {
        if (TaxYears.Any(y => y is < 1990 or > 2100)) { throw Refuse("refused", "Tax years must be between 1990 and 2100.", "Use four-digit years."); }
        if (!RefreshOnce && TaxYears.Count == 0) { throw Refuse("refused", "refresh_once is off but no tax years were given.", "Name tax years or enable refresh_once."); }
        if (Scope is ScopeKind.One or ScopeKind.List && Clients.Count == 0) { throw Refuse("empty_scope", "No client ids were given.", "Check the client ids or the filter."); }
        if (Scope == ScopeKind.One && Clients.Count != 1) { throw Refuse("refused", "scope 'one' takes exactly one client id.", "Use scope 'list' for several."); }
        string[] keys = ["program", "year", "outcome", "scope", "status", "near", "band", "state", "unassessed", "unavailable"];
        if (Filter.Any(p => !keys.Contains(p.Key, StringComparer.Ordinal)
            || p.Value is PyDict or IReadOnlyList<object?> || p.Value is string text && text.Length > 64))
        {
            throw Refuse("refused", "The filter contains an unknown key or a non-scalar/oversized value.", "Use short portfolio filter values.");
        }
    }

    internal static DraftsRunsRefusalException Refuse(string code, string reason, string remedy, int status = 422) =>
        new(status, new { detail = $"{reason} {remedy}", code, reason, remedy });
}
