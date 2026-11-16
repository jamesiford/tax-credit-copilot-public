using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>A sibling supplies trusted application facts, never HTTP responses, recordings or model prose.</summary>
public interface ICapabilityReadBridge
{
    /// <summary>Returns the named brief contract below, with the run/trail evidence captured by its owner.</summary>
    Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken);
}

/// <summary>Facts and provenance are kept together so the envelope cannot silently lose its derivation.</summary>
public sealed record CapabilityRead(JsonObject Facts, JsonObject? Provenance = null,
    IReadOnlyList<string>? Warnings = null, JsonArray? Blocks = null,
    IReadOnlyList<string>? UserOnlyFacts = null);

/// <summary>Only a validated application command can preview or commit a change.</summary>
public interface ICapabilityWriteBridge
{
    /// <summary>Builds and validates the owner's command, then returns {before,after}; no business state is changed.</summary>
    Task<JsonObject> PreviewAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken);
    /// <summary>Sends the owner's command through its mediator, including writer authorization and durable audit.</summary>
    Task<JsonObject> CommitAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken);
}

/// <summary>Explicit integration inventory instead of speculative copies of sibling calculations.</summary>
public static class CapabilityDependencies
{
    /// <summary>Contract names identify the exact expected application service owned outside this feature.</summary>
    public static (string Owner, string Service) Read(string tool) => tool switch
    {
        "book_rank" => ("ReadsCalc", "portfolio_page: priority asc, all years; {items,total_clients,assessed_clients}"),
        "client_eligibility" => ("ReadsCalc", "resolve_statute + chat_client_context + chat_state_credit: {snapshot,credit}, captured run/trail"),
        "client_at_risk" => ("ReadsCalc", "chat_jobs_at_risk: counted cohort fragility brief, resolved statute"),
        "client_discovery" => ("ReadsCalc", "discover_credits: {hits}, excluding selected state's programmes"),
        "simulate" => ("ReadsCalc", "simulate_unit: deterministic before/after, resolved fiscal statute"),
        "calc_walkthrough" => ("ReadsCalc", "calculation_walk: trail rows and SHA-256 from recorded calculation"),
        "employee_drill" => ("ReadsCalc", "get_employee_drill: token-scoped Gold read, resolved statute, explicit not_available"),
        "findings_list" => ("ReadsCalc", "list_findings: client/year decisions and recorded finding evidence"),
        "program_catalog" => ("ClaimsDrafts", "ListProgramCatalogQuery / GetProgramDetailQuery: registry validation and engagement counts"),
        "run_batch_list" => ("Runs", "ListRunBatchesQuery: client-visible batch summaries, progress and total"),
        "run_batch_status" => ("Runs", "GetRunBatchQuery + ListRunBatchItemsQuery: client-visible status, worker health and grouped failures"),
        "claim_package_link" => ("ClaimsDrafts", "package download tickets: person-bound single-use audited link"),
        "claim_package_redeem" => ("ClaimsDrafts", "package ticket redemption: expected user verified before atomic spend"),
        _ => ("ReadsCalc", tool),
    };

    /// <summary>Every write must bind one of these services before prepare can mint a token.</summary>
    public static (string Owner, string Service) Write(string change) => change switch
    {
        "finding_resolve" => ("ReadsCalc", "ResolveFindingCommand and pure preview"),
        "finding_reopen" => ("ReadsCalc", "ReopenFindingCommand and pure preview"),
        "claim_transition" => ("ClaimsDrafts", "TransitionClaimCommand and pure preview"),
        "claim_record" => ("ClaimsDrafts", "RecordClaimCommand and pure preview"),
        "engagement_set" => ("ClaimsDrafts", "SetEngagementCommand and pure preview"),
        "base_year_set" => ("ReadsCalc", "SetBaseYearCommand and recalculation preview"),
        "claim_package_create" => ("ClaimsDrafts", "CreateClaimPackageCommand and pure preview"),
        "run_batch" => ("Runs", "CreateRunBatchCommand and resolved scope preview"),
        _ => ("Unknown", change),
    };
}

internal sealed class MissingCapabilityReadBridge : ICapabilityReadBridge
{
    public Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken)
    {
        var (owner, service) = CapabilityDependencies.Read(capability);
        throw CapabilityException.Missing(owner, service);
    }
}

internal sealed class MissingCapabilityWriteBridge : ICapabilityWriteBridge
{
    public Task<JsonObject> PreviewAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken) =>
        throw Missing(change);
    public Task<JsonObject> CommitAsync(string change, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken) =>
        throw Missing(change);
    private static CapabilityException Missing(string change)
    {
        var (owner, service) = CapabilityDependencies.Write(change);
        return CapabilityException.Missing(owner, service);
    }
}
