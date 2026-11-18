using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Version-conditional draft replacement and immutable events in one transaction; drafts never become calculation authority.</summary>
public sealed class ProgramDraftRepository(PersistenceDatabase database) : IProgramDraftRepository
{
    /// <summary>Indicates stored drafts and events survive restart.</summary>
    public bool IsDurable { get; } = true;

    /// <inheritdoc />
    public void Create(ProgramDraft draft, DraftEvent draftEvent)
    {
        CheckEvent(draft, draftEvent);
        database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT draft_id FROM {ops.program_draft} WHERE draft_id = ? "
                + "OR (proposed_code = ? AND status NOT IN ('withdrawn', 'exported'))", draft.DraftId, draft.ProposedCode).Count != 0)
            {
                throw new DraftConflict("A draft with this identity or a live draft for this code already exists.");
            }

            session.InsertExempt(SqlExemption.ChannelIdentity, "ops.program_draft", ProgramDraftRows.Columns, [ProgramDraftRows.Values(session, draft)]);
            WriteDocuments(session, draft);
            Append(session, draftEvent);
            return true;
        });
    }

    /// <inheritdoc />
    public ProgramDraft? Get(string draftId) => database.Transact(session =>
    {
        var found = session.QueryExempt(SqlExemption.ChannelIdentity, ProgramDraftRows.Select + " WHERE draft_id = ?", draftId);
        return found.Count == 0 ? null : Hydrate(session, found.Single(), documents: true);
    });

    /// <inheritdoc />
    public void Save(ProgramDraft draft, long expectedVersion, DraftEvent draftEvent)
    {
        CheckEvent(draft, draftEvent);
        if (draft.Version != expectedVersion + 1)
        {
            throw new DraftConflict("A saved draft must advance the version exactly once.");
        }

        database.Transact(session =>
        {
            var columns = ProgramDraftRows.Columns.Skip(2).ToArray();
            var args = ProgramDraftRows.Values(session, draft).Skip(2).Concat([draft.DraftId, expectedVersion, draft.ProposedCode]).ToArray();
            var changed = session.ExecuteExempt(SqlExemption.ChannelIdentity, "UPDATE {ops.program_draft} SET "
                + string.Join(", ", columns.Select(column => column + " = ?")) + " WHERE draft_id = ? AND version = ? AND proposed_code = ?", args);
            if (changed != 1)
            {
                throw new DraftConflict("The draft changed since it was read; reload before retrying.");
            }

            WriteDocuments(session, draft);
            Append(session, draftEvent);
            return true;
        });
    }

    /// <inheritdoc />
    public (IReadOnlyList<ProgramDraft> Items, long Total) ListDrafts(string? status = null, long limit = 50, long offset = 0)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(limit);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(limit, 1000);
        ArgumentOutOfRangeException.ThrowIfNegative(offset);
        return database.Transact(session =>
        {
            var where = string.IsNullOrEmpty(status) ? "" : " WHERE status = ?";
            object?[] args = string.IsNullOrEmpty(status) ? [] : [status];
            var count = session.Dialect is SqliteDialect ? "COUNT(*)" : "COUNT_BIG(*)";
            var total = new OpsRow(session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT " + count + " AS n FROM {ops.program_draft}" + where, args)[0]).Long("n");
            if (offset >= total)
            {
                return ((IReadOnlyList<ProgramDraft>)Array.Empty<ProgramDraft>(), total);
            }

            var rows = session.QueryExempt(SqlExemption.ChannelIdentity,
                session.Dialect.Page(ProgramDraftRows.Select + where + " ORDER BY updated_at DESC, draft_id", (int)limit, offset), args);
            return ((IReadOnlyList<ProgramDraft>)rows.Select(row => Hydrate(session, row, documents: false)).ToArray(), total);
        });
    }

    /// <inheritdoc />
    public IReadOnlyList<DraftEvent> Events(string draftId)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT draft_id, seq, event_type, actor, at, from_status, to_status, detail_json "
            + "FROM {ops.program_draft_event} WHERE draft_id = ? ORDER BY seq", draftId).Select(values =>
            {
                var r = new OpsRow(values);
                return new DraftEvent
                {
                    DraftId = r.Required("draft_id"),
                    Seq = r.Long("seq"),
                    EventType = r.Required("event_type"),
                    Actor = r.Required("actor"),
                    At = r.Instant("at")!.Value,
                    FromStatus = r.Text("from_status"),
                    ToStatus = r.Text("to_status"),
                    Detail = r.Document("detail_json") ?? new PyDict(),
                };
            }).ToArray();
    }

    /// <inheritdoc />
    public ProgramDraft? LiveForCode(string proposedCode) => database.Transact(session =>
    {
        var found = session.QueryExempt(SqlExemption.ChannelIdentity, ProgramDraftRows.Select
            + " WHERE proposed_code = ? AND status NOT IN ('withdrawn', 'exported') ORDER BY created_at, draft_id", proposedCode);
        return found.Count == 0 ? null : Hydrate(session, found.Single(), documents: true);
    });

    private static void WriteDocuments(SqlSession session, ProgramDraft draft)
    {
        if (draft.Years.Count > ProgramDraftRules.MaxYearDocuments || draft.Years.Keys.Any(key => key == "pack" || key.Length > 16))
        {
            throw new ArgumentException("Draft year document keys or count exceed the storage contract.", nameof(draft));
        }

        session.ExecuteExempt(SqlExemption.ChannelIdentity, "DELETE FROM {ops.program_draft_document} WHERE draft_id = ?", draft.DraftId);
        var documents = new List<KeyValuePair<string, object?>>();
        if (draft.Pack is not null)
        {
            documents.Add(new("pack", draft.Pack));
        }

        documents.AddRange(draft.Years);
        foreach (var pair in documents)
        {
            var text = ProgramDraftRows.Document((PyDict)pair.Value!)!;
            var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
            session.InsertExempt(SqlExemption.ChannelIdentity, "ops.program_draft_document",
                ["draft_id", "doc_key", "content_json", "content_sha256"], [new object?[] { draft.DraftId, pair.Key, text, hash }]);
        }
    }

    private static void Append(SqlSession session, DraftEvent draftEvent)
    {
        var last = new OpsRow(session.QueryExempt(SqlExemption.ChannelIdentity,
            "SELECT MAX(seq) AS n FROM {ops.program_draft_event} WHERE draft_id = ?", draftEvent.DraftId)[0]);
        var text = OpsRow.Json(draftEvent.Detail);
        if (text is not null && text.EnumerateRunes().Count() > 4000)
        {
            throw new ArgumentException("The draft event detail exceeds its storage limit.", nameof(draftEvent));
        }

        session.InsertExempt(SqlExemption.ChannelIdentity, "ops.program_draft_event",
            ["draft_id", "seq", "event_type", "actor", "at", "from_status", "to_status", "detail_json"],
            [new object?[] { draftEvent.DraftId, last.Long("n") + 1, draftEvent.EventType, draftEvent.Actor,
                OpsRow.Timestamp(session, draftEvent.At), draftEvent.FromStatus, draftEvent.ToStatus, text }]);
    }

    private static ProgramDraft Hydrate(SqlSession session, IReadOnlyDictionary<string, object?> row, bool documents)
    {
        PyDict? pack = null;
        var years = new PyDict();
        if (documents)
        {
            foreach (var values in session.QueryExempt(SqlExemption.ChannelIdentity,
                "SELECT doc_key, content_json, content_sha256 FROM {ops.program_draft_document} WHERE draft_id = ? ORDER BY doc_key", row["draft_id"]))
            {
                var r = new OpsRow(values);
                var text = r.Required("content_json");
                var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
                if (!string.Equals(hash, r.Required("content_sha256").Trim(), StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Stored draft document does not match its digest.");
                }

                if (r.Required("doc_key") == "pack")
                {
                    pack = (PyDict)PyJson.Loads(text)!;
                }
                else
                {
                    years.Add(r.Required("doc_key"), PyJson.Loads(text));
                }
            }
        }

        return ProgramDraftRows.Draft(row, pack, years);
    }

    private static void CheckEvent(ProgramDraft draft, DraftEvent draftEvent)
    {
        ArgumentNullException.ThrowIfNull(draft);
        ArgumentNullException.ThrowIfNull(draftEvent);
        if (draftEvent.DraftId != draft.DraftId)
        {
            throw new ArgumentException("An event must belong to the draft being stored.", nameof(draftEvent));
        }
    }
}
