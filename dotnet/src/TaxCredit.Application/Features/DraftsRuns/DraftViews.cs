using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static class DraftViews
{
    internal static string FileName(ProgramDraft draft)
    {
        var code = draft.ProposedCode.ToLowerInvariant();
        var state = (draft.State ?? "").ToLowerInvariant();
        var prefix = state + "_";
        var slug = state.Length > 0 && code.StartsWith(prefix, StringComparison.Ordinal) && code.Length > prefix.Length ? code[prefix.Length..] : code;
        return $"{state}_{slug}.json";
    }

    internal static bool Current(ProgramDraft draft) => draft.Validation is { } validation
        && Equals(validation["content_sha256"], draft.ContentSha256);

    internal static PyDict Summary(ProgramDraft draft) => new PyDict().Add("draft_id", draft.DraftId).Add("proposed_code", draft.ProposedCode)
        .Add("name", draft.Name).Add("jurisdiction_level", draft.JurisdictionLevel).Add("state", draft.State).Add("status", draft.Status.Value())
        .Add("version", draft.Version).Add("created_by", draft.CreatedBy).Add("created_at", draft.CreatedAt.IsoFormat())
        .Add("updated_by", draft.UpdatedBy).Add("updated_at", draft.UpdatedAt.IsoFormat()).Add("pack_file", FileName(draft))
        .Add("validation_errors", draft.Validation?["errors"]).Add("verification", "not_verified").Add("has_runtime_authority", false);

    internal static PyDict Detail(ProgramDraft draft) => Summary(draft)
        .Add("documents", new PyDict().Add("pack", draft.Pack).Add("years", draft.Years)).Add("content_sha256", draft.ContentSha256)
        .Add("validation", draft.Validation).Add("validation_current", Current(draft))
        .Add("review", new PyDict().Add("requested_by", draft.ReviewRequestedBy).Add("reviewer", draft.Reviewer).Add("decision", draft.Decision)
            .Add("comment", draft.DecisionComment).Add("decided_at", draft.DecidedAt?.IsoFormat()).Add("approved_sha256", draft.ApprovedSha256))
        .Add("export", new PyDict().Add("exported_at", draft.ExportedAt?.IsoFormat()).Add("bundle_sha256", draft.ExportSha256))
        .Add("allowed_actions", Actions(draft)).Add("events", new List<object?>());

    internal static PyDict Event(DraftEvent entry) => new PyDict().Add("seq", entry.Seq).Add("event_type", entry.EventType)
        .Add("actor", entry.Actor).Add("at", entry.At.IsoFormat()).Add("from_status", entry.FromStatus).Add("to_status", entry.ToStatus).Add("detail", entry.Detail);

    private static List<object?> Actions(ProgramDraft draft)
    {
        var actions = new List<object?>();
        if (DraftStatusExtensions.Editable.Contains(draft.Status))
        {
            actions.AddRange(["edit", "validate"]);
            if (Current(draft) && draft.Validation!["valid"] is true) { actions.Add("request_review"); }
        }
        if (draft.Status == DraftStatus.ReadyForReview) { actions.AddRange(["approve", "request_changes"]); }
        if (draft.Status is DraftStatus.ApprovedForExport or DraftStatus.Exported) { actions.Add("export"); }
        if (draft.Status != DraftStatus.Withdrawn && draft.Pack is not null) { actions.Add("preview"); }
        if (draft.Status is not (DraftStatus.Withdrawn or DraftStatus.Exported)) { actions.Add("withdraw"); }
        return actions;
    }
}
