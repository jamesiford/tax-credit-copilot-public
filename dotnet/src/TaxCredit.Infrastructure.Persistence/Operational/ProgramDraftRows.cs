using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

internal static class ProgramDraftRows
{
    internal static readonly string[] Columns =
    [
        "draft_id", "proposed_code", "name", "jurisdiction_level", "state", "status", "version", "created_by",
        "created_at", "updated_by", "updated_at", "validation_json", "review_requested_by", "reviewer", "decision",
        "decision_comment", "decided_at", "approved_sha256", "exported_at", "export_sha256",
    ];

    internal static string Select => "SELECT " + string.Join(", ", Columns) + " FROM tcc_ops.program_draft";

    internal static object?[] Values(SqlSession session, ProgramDraft draft) =>
    [
        draft.DraftId, draft.ProposedCode, draft.Name, draft.JurisdictionLevel, draft.State, draft.Status.Value(), draft.Version,
        draft.CreatedBy, OpsRow.Timestamp(session, draft.CreatedAt), draft.UpdatedBy, OpsRow.Timestamp(session, draft.UpdatedAt), Document(draft.Validation),
        draft.ReviewRequestedBy, draft.Reviewer, draft.Decision, draft.DecisionComment, OpsRow.Timestamp(session, draft.DecidedAt),
        draft.ApprovedSha256, OpsRow.Timestamp(session, draft.ExportedAt), draft.ExportSha256,
    ];

    internal static string? Document(PyDict? document)
    {
        if (document is null)
        {
            return null;
        }

        var text = ProgramDraftRules.CanonicalJson(document);
        if (text.EnumerateRunes().Count() > ProgramDraftRules.MaxDocumentChars)
        {
            throw new ArgumentException("The draft document exceeds the storage limit.", nameof(document));
        }

        return text;
    }

    internal static ProgramDraft Draft(IReadOnlyDictionary<string, object?> values, PyDict? pack, PyDict years)
    {
        var r = new OpsRow(values);
        return new ProgramDraft
        {
            DraftId = r.Required("draft_id"),
            ProposedCode = r.Required("proposed_code"),
            Name = r.Required("name"),
            JurisdictionLevel = r.Required("jurisdiction_level"),
            State = r.Text("state"),
            Status = DraftStatusExtensions.FromValue(r.Required("status")),
            Version = r.Long("version"),
            CreatedBy = r.Required("created_by"),
            CreatedAt = r.Instant("created_at")!.Value,
            UpdatedBy = r.Required("updated_by"),
            UpdatedAt = r.Instant("updated_at")!.Value,
            Pack = pack,
            Years = years,
            Validation = r.Document("validation_json"),
            ReviewRequestedBy = r.Text("review_requested_by"),
            Reviewer = r.Text("reviewer"),
            Decision = r.Text("decision"),
            DecisionComment = r.Text("decision_comment"),
            DecidedAt = r.Instant("decided_at"),
            ApprovedSha256 = r.Text("approved_sha256"),
            ExportedAt = r.Instant("exported_at"),
            ExportSha256 = r.Text("export_sha256"),
        };
    }
}
