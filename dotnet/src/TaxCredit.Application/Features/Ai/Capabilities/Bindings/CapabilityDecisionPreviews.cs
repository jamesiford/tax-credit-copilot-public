using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Pure domain transitions validate the proposed decision without allocating production identities.</summary>
public sealed class CapabilityDecisionPreviews(IClaimRepository claims, IFindingRepository findings)
{
    private static readonly string[] ClaimFields = ["status", "provenance", "identified_usd", "claimed_usd",
        "certified_usd", "decline_reason", "decided_by", "filing_reference"];

    internal JsonObject Finding(string change, JsonObject a, ApiPrincipal principal)
    {
        var id = Text(a, "finding_id")!;
        if (string.IsNullOrEmpty(id)) { throw CapabilityException.Invalid("finding_id is required."); }
        var resolve = change == "finding_resolve";
        var resolution = Text(a, "resolution");
        if (resolve && (resolution is not ("accept" or "assign" or "drop" or "flag")
            || resolution == "assign" && string.IsNullOrEmpty(Text(a, "keep_worksite"))))
        {
            throw CapabilityException.Invalid("A valid resolution and keep_worksite for assign are required.");
        }
        var current = findings.Live(Client(a), resolve ? Year(a) : null).FirstOrDefault(row => row.FindingId == id);
        var before = current is null ? null : Select(Object(current.ToDict()), "resolution", "note", "decided_by");
        var after = resolve
            ? new JsonObject { ["finding_id"] = id, ["resolution"] = resolution, ["note"] = Text(a, "note"), ["decided_by"] = principal.Actor }
            : new JsonObject { ["finding_id"] = id, ["resolution"] = null, ["requires_decision"] = true };
        return Preview(before, after);
    }

    internal JsonObject Claim(string change, JsonObject a, ApiPrincipal principal)
    {
        var current = claims.Current(Client(a), Text(a, "program_code")!, Year(a));
        var status = ClaimEnumExtensions.StatusFromValue(Text(a, "status")!);
        ProgramClaim next;
        if (change == "claim_transition")
        {
            if (current is null) { throw NotCalculated("No recorded claim to transition."); }
            next = current.TransitionTo(status, new TransitionOptions
            {
                DecidedBy = principal.Actor,
                DeclineReason = Text(a, "decline_reason"),
            }, new ClaimClock(() => current.ClaimId ?? "", () => current.EffectiveFrom));
        }
        else
        {
            next = ProgramClaim.Create(new ClaimSpec
            {
                ClientId = Client(a),
                ProgramCode = Text(a, "program_code"),
                TaxYear = Year(a),
                Status = status,
                Provenance = Provenance.ClientAsserted,
                DecidedBy = principal.Actor,
                ClaimId = "",
                EffectiveFrom = new TaxCredit.Domain.Numerics.PyDateTime(new DateOnly(2000, 1, 1), 0, 0, 0, 0, 0),
            });
            if (current is not null && Equivalent(current, next))
            {
                throw new CapabilityException(409, "rejected", "An identical claim is already recorded; use transition.");
            }
        }
        return Preview(current is null ? null : Select(Object(current.ToDict()), ClaimFields),
            Select(Object(next.ToDict()), ClaimFields)!);
    }

    internal JsonObject Engagement(JsonObject a, ApiPrincipal principal)
    {
        var scope = ClaimEnumExtensions.ScopeFromValue(Text(a, "scope")!).Value();
        var code = Text(a, "program_code")!.ToUpperInvariant();
        if (string.IsNullOrWhiteSpace(code)) { throw CapabilityException.Invalid("program_code is required."); }
        var current = claims.Engagements(Client(a)).FirstOrDefault(row => row.ProgramCode == code);
        var before = current is null ? null : Select(Object(current.ToDict()), "scope", "note", "set_by");
        return Preview(before, new JsonObject { ["scope"] = scope, ["note"] = Text(a, "note"), ["set_by"] = principal.Actor });
    }

    private static bool Equivalent(ProgramClaim left, ProgramClaim right) =>
        left.ToSpec() with { ClaimId = null, EffectiveFrom = null, EffectiveTo = null, DecidedAt = null }
        == right.ToSpec() with { ClaimId = null, EffectiveFrom = null, EffectiveTo = null, DecidedAt = null };
}
