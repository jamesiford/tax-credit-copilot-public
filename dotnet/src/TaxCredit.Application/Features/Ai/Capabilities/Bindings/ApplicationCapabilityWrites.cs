using System.Text.Json.Nodes;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Existing capability confirmations surround real commands, not a second write pipeline.</summary>
public sealed class ApplicationCapabilityWrites(IMediator mediator, CapabilityDecisionPreviews decisions,
    CapabilityOperationalPreviews operations) : ICapabilityWriteBridge
{
    /// <inheritdoc />
    public async Task<JsonObject> PreviewAsync(string change, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken)
    {
        _ = Command(change, arguments, principal);
        return change switch
        {
            "finding_resolve" or "finding_reopen" => decisions.Finding(change, arguments, principal),
            "claim_record" or "claim_transition" => decisions.Claim(change, arguments, principal),
            "engagement_set" => decisions.Engagement(arguments, principal),
            "base_year_set" => await operations.BaseYear(arguments, cancellationToken).ConfigureAwait(false),
            "claim_package_create" => operations.Package(arguments),
            "run_batch" => await operations.Batch(arguments, cancellationToken).ConfigureAwait(false),
            _ => throw CapabilityException.Invalid("Unknown write."),
        };
    }

    /// <inheritdoc />
    public async Task<JsonObject> CommitAsync(string change, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken)
    {
        var result = Object(await mediator.Send(Command(change, arguments, principal), cancellationToken).ConfigureAwait(false));
        if (change != "claim_package_create") { return result; }
        var fields = new[] { "artifact_id", "client_id", "tax_year", "run_id", "file_name", "sha256", "size_bytes", "rows" };
        var package = new JsonObject(fields.Select(field => KeyValuePair.Create(field, result[field]?.DeepClone())));
        package["download_path"] = "/api/clients/" + Client(arguments).ToString(System.Globalization.CultureInfo.InvariantCulture)
            + "/artifacts/" + result["artifact_id"]!.GetValue<string>();
        return package;
    }

    private static ICommand<object> Command(string change, JsonObject a, ApiPrincipal p) => change switch
    {
        "finding_resolve" => new ResolveFinding(Text(a, "finding_id")!, Client(a), Year(a),
            Text(a, "resolution")!, Text(a, "keep_worksite"), Text(a, "note"), p.Actor),
        "finding_reopen" => new ReopenFinding(Text(a, "finding_id")!, Client(a), p.Actor),
        "claim_transition" => new TransitionClaim(Client(a), Text(a, "program_code")!, Year(a), Body(a), p.Actor),
        "claim_record" => new RecordClaim(Body(RecordBody(a)), p.Actor),
        "engagement_set" => new SetEngagement(Client(a), Text(a, "program_code")!, Text(a, "scope")!, Text(a, "note"), p.Actor),
        "base_year_set" => new SetBaseYearCommand(Client(a), Text(a, "unit_id")!, Body(a)),
        "claim_package_create" => new CreatePackage(Client(a), Year(a), p.Actor),
        "run_batch" => new StartBatchCommand(Body(CapabilityOperationalPreviews.BatchBody(a))),
        _ => throw CapabilityException.Invalid("Unknown write."),
    };

    private static JsonObject RecordBody(JsonObject args)
    {
        var body = (JsonObject)args.DeepClone();
        body["provenance"] = "client_asserted";
        return body;
    }
}
