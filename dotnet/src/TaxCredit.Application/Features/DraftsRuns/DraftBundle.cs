using System.IO.Compression;
using System.Security.Cryptography;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

internal sealed record DraftBundle(byte[] Bytes, string Sha256, PyDict Manifest)
{
    private static readonly HashSet<string> History = ["created", "edited", "validated", "review_requested", "approved", "changes_requested"];

    internal static DraftBundle Build(ProgramDraft draft, IReadOnlyList<DraftEvent> events)
    {
        var files = new SortedDictionary<string, byte[]>(PyStr.Comparer);
        var name = DraftViews.FileName(draft);
        files.Add("rules/" + name, Json(draft.Pack));
        foreach (var (year, doc) in draft.Years) { files.Add($"rules/{name[..^5]}/{year}.json", Json(doc)); }
        files.Add("registry-patch.json", Json(new PyDict().Add("add_to", "backend/rules/registry/programs.json")
            .Add("programs", new List<object?> { Registry(draft) })));
        files.Add("validation-report.json", Json(new PyDict().Add("note", "Valid means well-formed, not verified.").Add("result", draft.Validation)));
        files.Add("review-record.json", Json(new PyDict().Add("requested_by", draft.ReviewRequestedBy).Add("reviewer", draft.Reviewer)
            .Add("decision", draft.Decision).Add("comment", draft.DecisionComment).Add("decided_at", draft.DecidedAt?.IsoFormat())
            .Add("approved_content_sha256", draft.ApprovedSha256).Add("history", events.Where(e => History.Contains(e.EventType))
                .Select(e => (object?)new PyDict().Add("seq", e.Seq).Add("event", e.EventType).Add("actor", e.Actor)
                    .Add("at", e.At.IsoFormat()).Add("to_status", e.ToStatus)).ToList())));
        files.Add("COMMIT-CHECKLIST.md", PyUtf8.Encode(DraftChecklist.Text(draft, files.Keys.ToArray(), name)));
        var manifest = new PyDict().Add("kind", "program-draft-bundle").Add("schema_version", 1L).Add("draft_id", draft.DraftId)
            .Add("proposed_code", draft.ProposedCode).Add("name", draft.Name).Add("state", draft.State).Add("content_sha256", draft.ContentSha256)
            .Add("approved_sha256", draft.ApprovedSha256).Add("verification", "not_verified").Add("has_runtime_authority", false)
            .Add("changelog_line", DraftChecklist.Changelog(draft)).Add("files", files.Select(p => (object?)new PyDict()
                .Add("path", p.Key).Add("sha256", Hash(p.Value)).Add("bytes", (long)p.Value.Length)).ToList());
        files.Add("manifest.json", Json(manifest));
        using var buffer = new MemoryStream();
        using (var zip = new ZipArchive(buffer, ZipArchiveMode.Create, leaveOpen: true))
        {
            foreach (var (path, bytes) in files)
            {
                var entry = zip.CreateEntry(path, CompressionLevel.Optimal);
                entry.LastWriteTime = new DateTimeOffset(1980, 1, 1, 0, 0, 0, TimeSpan.Zero);
                entry.ExternalAttributes = 0x1a4 << 16;
                using var stream = entry.Open();
                stream.Write(bytes);
            }
        }
        var output = buffer.ToArray();
        return new(output, Hash(output), manifest);
    }

    internal static byte[] Json(object? value) => PyUtf8.Encode(Pretty(value, 0) + "\n");
    internal static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private static string Pretty(object? value, int depth)
    {
        var indent = new string(' ', (depth + 1) * 2);
        var close = new string(' ', depth * 2);
        if (value is PyDict map)
        {
            return map.Count == 0 ? "{}" : "{\n" + string.Join(",\n", map.OrderBy(p => p.Key, PyStr.Comparer)
                .Select(p => indent + PyJson.Dumps(p.Key, true, true, false) + ": " + Pretty(p.Value, depth + 1))) + "\n" + close + "}";
        }
        if (value is IReadOnlyList<object?> list)
        {
            return list.Count == 0 ? "[]" : "[\n" + string.Join(",\n", list.Select(item => indent + Pretty(item, depth + 1))) + "\n" + close + "]";
        }
        return PyJson.Dumps(value, true, true, false);
    }

    private static PyDict Registry(ProgramDraft draft) => new PyDict().Add("code", draft.ProposedCode).Add("name", draft.Name)
        .Add("jurisdiction", new PyDict().Add("level", draft.JurisdictionLevel).Add("code", draft.State)).Add("state", draft.State)
        .Add("pack_file", DraftViews.FileName(draft)).Add("lifecycle", "described")
        .Add("engine_profile", new PyDict().Add("credit_model", "per_net_new_job").Add("headcount_model", "one_zero"))
        .Add("notes", "Added from a reviewed draft. Statute values are not verified until a person verifies each against the primary source.");
}
