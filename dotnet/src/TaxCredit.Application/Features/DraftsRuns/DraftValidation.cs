using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Draft-specific identity, citation and privacy rules augment the same validator used by authored packs.</summary>
public sealed class DraftValidation(PackValidator validator, RuleLibrary rules, DraftCustomerData customerData)
{
    /// <summary>Returns the full finding set; storage is independently bounded without changing exact counts.</summary>
    public PyDict Validate(ProgramDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);
        var findings = new List<PyDict>();
        var registry = rules.LoadRegistry();
        if (registry.Get(draft.ProposedCode) is not null) { Error("draft", "code_registered", "proposed_code", "The code is already registered."); }
        if (registry.Entries.Any(e => e.PackFile == DraftViews.FileName(draft))) { Error("draft", "pack_file_registered", "proposed_code", "The pack file is already registered."); }
        if (Field(draft.Pack, "credit", "code") != draft.ProposedCode) { Error("pack", "code_mismatch", "credit/code", $"credit.code must be {draft.ProposedCode}"); }
        if (Field(draft.Pack, "jurisdiction", "code") != draft.State) { Error("pack", "state_mismatch", "jurisdiction/code", $"jurisdiction.code must be {draft.State}"); }
        if (draft.Pack is null) { Error("pack", "pack_missing", "", "The draft has no base pack yet."); }
        else
        {
            AddReport(draft.Pack, DraftViews.FileName(draft), "pack", "base", draft.Years.Count > 0);
            if (!Cited(Field(draft.Pack, "credit", "statutory_citation"))) { Error("pack", "citation_missing", "credit/statutory_citation", "Cite the statute this credit comes from."); }
            foreach (var (key, value) in draft.Years.OrderBy(p => p.Key, PyStr.Comparer))
            {
                var doc = (PyDict)value!;
                var where = "year " + key;
                AddReport(doc, key + ".json", where, "year", true);
                if (!doc.TryGetValue("tax_year", out var year) || TaxCredit.Domain.Gold.GoldValues.Str(year) != key) { Error(where, "year_mismatch", "tax_year", $"tax_year must be {key}."); }
                foreach (var block in new[] { "credit", "jurisdiction" })
                {
                    if (Field(doc, block, "code") != Field(draft.Pack, block, "code")) { Error(where, "year_pack_mismatch", block + "/code", block + ".code differs from the base pack."); }
                }
                if (!Cited(Field(doc, "_year_provenance", "source"))) { Error(where, "citation_missing", "_year_provenance/source", "Name the primary source this year's values come from."); }
            }
            if (draft.Years.Count == 0) { findings.Add(Finding("draft", "warning", "no_years", "years", "No year pack: described, not calculable, until a year is authored (ADR-005).")); }
            foreach (var (where, document) in DraftDocuments.All(draft))
            {
                foreach (var (path, text) in DraftDocuments.Strings(document).Where(p => p.Text.Trim().StartsWith("TODO", StringComparison.OrdinalIgnoreCase)))
                {
                    Error(where, "todo_placeholder", path, "Still holds scaffolding text: replace it with a cited value.");
                }
                if (document is PyDict map && map.ContainsKey("_verified")) { Error(where, "verified_claim", "_verified", "A draft cannot claim _verified."); }
            }
        }
        findings.AddRange(customerData.Scan(draft));
        var sorted = findings.OrderBy(f => Rank((string)f["severity"]!)).ThenBy(f => (string)f["file"]!, PyStr.Comparer)
            .ThenBy(f => (string)f["path"]!, PyStr.Comparer).Cast<object?>().ToList();
        return new PyDict().Add("content_sha256", draft.ContentSha256).Add("valid", Count("error") == 0).Add("errors", Count("error"))
            .Add("warnings", Count("warning")).Add("infos", Count("info")).Add("findings", sorted).Add("truncated", false).Add("verification", "not_verified");

        long Count(string severity) => findings.LongCount(f => Equals(f["severity"], severity));
        void Error(string file, string code, string path, string message) => findings.Add(Finding(file, "error", code, path, message));
        void AddReport(PyDict doc, string name, string file, string kind, bool hasYears) =>
            findings.AddRange(validator.ValidateDocument(doc, name, kind, hasYears).Issues.Select(i => Finding(file, i.Severity, i.Code, i.Path, i.Message)));
    }

    internal static PyDict Stored(PyDict result)
    {
        var all = (IReadOnlyList<object?>)result["findings"]!;
        var kept = all.Take(40).Cast<PyDict>().Select(f => (object?)FeatureValues.Copy(f.Select(p =>
            new KeyValuePair<string, object?>(p.Key, p.Key == "message" ? PyStr.Prefix((string)p.Value!, 160) : p.Value)))).ToList();
        var stored = FeatureValues.Copy(result);
        stored.Set("findings", kept).Set("truncated", all.Count > kept.Count);
        while (kept.Count > 0 && PyJson.Dumps(stored, true, true, false).EnumerateRunes().Count() > ProgramDraftRules.MaxDocumentChars)
        {
            kept.RemoveAt(kept.Count - 1);
            stored.Set("truncated", true);
        }
        return stored;
    }

    internal static PyDict Finding(string file, string severity, string code, string path, string message) =>
        new PyDict().Add("file", file).Add("severity", severity).Add("code", code).Add("path", path).Add("message", message);
    private static int Rank(string severity) => severity == "error" ? 0 : severity == "warning" ? 1 : 2;
    private static string? Field(PyDict? doc, string block, string key) => doc is not null ? FeatureValues.Text(FeatureValues.Map(doc, block), key) : null;
    private static bool Cited(string? value) => !string.IsNullOrWhiteSpace(value) && !value.Trim().StartsWith("TODO", StringComparison.OrdinalIgnoreCase);
}
