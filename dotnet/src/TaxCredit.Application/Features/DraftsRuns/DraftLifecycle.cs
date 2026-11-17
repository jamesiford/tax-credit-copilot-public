using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Every transition saves its expected version and event together; no transition activates a program.</summary>
public sealed class DraftLifecycle(IProgramDraftRepository repository, RuleLibrary rules, IClock clock, IIdSource ids,
    IApiPrincipalAccessor principals, IRuntimeConfiguration configuration, DraftValidation validation, DraftCustomerData customerData)
{
    internal ProgramDraft Load(string id) => repository.Get(id) ?? throw new DraftNotFound("No such draft.");

    internal ProgramDraft Create(PyDict body)
    {
        var code = FeatureValues.Text(body, "code", "")!.Trim().ToUpperInvariant();
        var state = FeatureValues.Text(body, "state", "")!.Trim().ToUpperInvariant();
        var name = FeatureValues.Text(body, "name", "")!.Trim();
        if (!DraftDocuments.Code().IsMatch(code) || !DraftDocuments.State().IsMatch(state) || name.Length == 0) { throw new DraftInvalid("A draft requires a valid program code, two-letter state and name."); }
        if (rules.LoadRegistry().Get(code) is not null || repository.LiveForCode(code) is not null) { throw new DraftConflict("This program is registered or already has an open draft."); }
        var actor = Actor(body);
        var at = FeatureValues.Now(clock);
        var draft = new ProgramDraft
        {
            DraftId = ids.NewId().ToString("N"),
            ProposedCode = code,
            State = state,
            Name = name,
            JurisdictionLevel = "state",
            Version = 1,
            Status = DraftStatus.Draft,
            CreatedBy = actor,
            UpdatedBy = actor,
            CreatedAt = at,
            UpdatedAt = at,
            Pack = DraftScaffold.Base(code, state, name),
            Years = DraftScaffold.Years(code, state, name, FeatureValues.Years(body, "years"))
        };
        DraftDocuments.Check(draft.Pack, draft.Years);
        repository.Create(draft, Event(draft, "created", actor, at, draft.Status,
            new PyDict().Add("years", draft.Years.Keys.Order(PyStr.Comparer).Cast<object?>().ToList())));
        return draft;
    }

    internal ProgramDraft Edit(string id, PyDict body)
    {
        var old = Load(id);
        if (old.Version != FeatureValues.Integer(body, "expected_version")) { throw new DraftConflict("The draft version changed; reload it."); }
        Editable(old);
        var pack = body.TryGetValue("pack", out var raw) && raw is not null ? raw as PyDict ?? throw new DraftInvalid("The base pack must be an object.") : null;
        var years = FeatureValues.Map(body, "years");
        DraftDocuments.Check(pack, years);
        var changed = old with { Pack = pack, Years = years, Name = FeatureValues.Text(body, "name")?.Trim() is { Length: > 0 } name ? name : old.Name, Status = DraftStatus.Draft };
        var detail = new PyDict().Add("content_sha256", changed.ContentSha256);
        var leaks = customerData.Scan(changed).Count;
        if (leaks > 0) { detail.Add("customer_data_findings", (long)leaks); }
        return Save(old, changed, body, "edited", detail);
    }

    internal PyDict Validate(string id, PyDict body)
    {
        var old = Load(id);
        Editable(old);
        var result = validation.Validate(old);
        var changed = Save(old, old with { Validation = DraftValidation.Stored(result), Status = result["valid"] is true ? DraftStatus.Draft : DraftStatus.NeedsChanges },
            body, "validated", new PyDict().Add("errors", result["errors"]).Add("warnings", result["warnings"]).Add("content_sha256", result["content_sha256"]));
        return DraftViews.Detail(changed).Set("validation", result);
    }

    internal ProgramDraft RequestReview(string id, PyDict body)
    {
        var old = Load(id);
        Editable(old);
        if (!DraftViews.Current(old) || old.Validation!["valid"] is not true) { throw new ReviewRefused("Validate the current documents and fix all errors before asking for review."); }
        return Save(old, old with { Status = DraftStatus.ReadyForReview, ReviewRequestedBy = Actor(body) }, body, "review_requested", new());
    }

    internal ProgramDraft Review(string id, PyDict body)
    {
        var old = Load(id);
        if (old.Status != DraftStatus.ReadyForReview) { throw new InvalidTransition("Only a draft ready for review can be reviewed."); }
        var decision = FeatureValues.Text(body, "decision");
        var comment = FeatureValues.Text(body, "comment")?.Trim();
        if (decision is not ("approve" or "request_changes")) { throw new DraftInvalid("A decision is approve or request_changes."); }
        if (decision == "request_changes" && string.IsNullOrEmpty(comment)) { throw new DraftInvalid("A request for changes needs a comment."); }
        if (RequiresSecondReviewer() && IsAuthor(old, Actor(body)))
        {
            throw new ReviewRefused("The reviewer must differ from the people who wrote and submitted the draft.");
        }
        var approve = decision == "approve";
        if (approve && !DraftViews.Current(old)) { throw new ReviewRefused("The documents changed since validation."); }
        return Save(old, old with
        {
            Status = approve ? DraftStatus.ApprovedForExport : DraftStatus.NeedsChanges,
            Reviewer = Actor(body),
            Decision = decision,
            DecisionComment = string.IsNullOrEmpty(comment) ? null : comment,
            DecidedAt = FeatureValues.Now(clock),
            ApprovedSha256 = approve ? old.ContentSha256 : null
        }, body, approve ? "approved" : "changes_requested", new PyDict().Add("comment", string.IsNullOrEmpty(comment) ? null : comment));
    }

    internal ProgramDraft Withdraw(string id, PyDict body)
    {
        var old = Load(id);
        if (old.Status is DraftStatus.Withdrawn or DraftStatus.Exported) { throw new InvalidTransition("An exported or withdrawn draft cannot be withdrawn."); }
        return Save(old, old with { Status = DraftStatus.Withdrawn }, body, "withdrawn", new PyDict().Add("reason", FeatureValues.Text(body, "reason")?.Trim() is { Length: > 0 } reason ? reason : null));
    }

    private bool IsAuthor(ProgramDraft draft, string actor)
    {
        var person = principals.Current ?? ApiPrincipal.Anonymous;
        var tenant = person.IsAgent ? person.ActingFor?.TenantId : person.TenantId;
        return repository.Events(draft.DraftId).Where(e => e.EventType is "created" or "edited" or "review_requested").Any(e =>
            e.Actor == actor || person.Authenticated && person.EffectiveOid is { Length: > 0 } oid
            && FeatureValues.Text(e.Detail, "actor_oid") == oid
            && (FeatureValues.Text(e.Detail, "actor_tenant") is not { } theirTenant || tenant is null || tenant == theirTenant));
    }

    internal ProgramDraft Save(ProgramDraft old, ProgramDraft changed, PyDict body, string kind, PyDict detail)
    {
        var actor = Actor(body);
        var at = FeatureValues.Now(clock);
        changed = changed with { Version = old.Version + 1, UpdatedBy = actor, UpdatedAt = at };
        repository.Save(changed, old.Version, Event(old, kind, actor, at, changed.Status, detail));
        return changed;
    }

    private DraftEvent Event(ProgramDraft old, string kind, string actor, PyDateTime at, DraftStatus target, PyDict detail)
    {
        var principal = principals.Current ?? ApiPrincipal.Anonymous;
        if (principal.Authenticated && principal.EffectiveOid is { Length: > 0 } oid)
        {
            detail.Add("actor_oid", oid).Add("actor_tenant", principal.IsAgent ? principal.ActingFor?.TenantId : principal.TenantId);
        }
        return new DraftEvent
        {
            DraftId = old.DraftId,
            Seq = 0,
            EventType = kind,
            Actor = actor,
            At = at,
            FromStatus = old.Status.Value(),
            ToStatus = target.Value(),
            Detail = detail
        };
    }

    private string Actor(PyDict body) => FeatureValues.Actor(principals, body);
    private bool RequiresSecondReviewer() => configuration.Get("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER")?.Trim().ToLowerInvariant() switch
    {
        null or "" => !string.Equals(configuration.Get("ENVIRONMENT")?.Trim(), "local", StringComparison.OrdinalIgnoreCase),
        "true" or "1" or "yes" or "on" => true,
        "false" or "0" or "no" or "off" => false,
        _ => throw new InvalidOperationException("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER must be a boolean.")
    };
    private static void Editable(ProgramDraft draft)
    {
        if (!DraftStatusExtensions.Editable.Contains(draft.Status)) { throw new InvalidTransition("This draft cannot be edited or submitted in its current state."); }
    }
}
