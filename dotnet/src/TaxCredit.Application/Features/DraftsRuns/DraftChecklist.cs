using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static class DraftChecklist
{
    internal static string Changelog(ProgramDraft draft)
    {
        var years = draft.Years.Count > 0 ? string.Join(", ", draft.Years.Keys.Order(PyStrComparer)) : "no authored year yet";
        return $"- Added program `{draft.ProposedCode}` ({draft.Name}, {draft.State}): rule pack and year packs for {years}. "
            + "Statute values are not verified until a person verifies each against the primary source; the program is "
            + "calculable only for authored years. Operators: deploy this release; no settings or migrations.";
    }

    internal static string Text(ProgramDraft draft, IReadOnlyList<string> files, string packFile)
    {
        var yearFiles = files.Where(f => f.StartsWith("rules/", StringComparison.Ordinal) && f.Count(c => c == '/') == 2).ToArray();
        var lines = new List<string>
        {
            $"# Commit checklist: {draft.ProposedCode} ({draft.Name})", "",
            "This bundle is a PROPOSAL. Nothing in it is verified, and importing it into a deployment does nothing until the files are",
            "committed and deployed (ADR-005). Statute stays human-authored and version controlled.", "",
            "## 1. Who must verify the statute (before anything else)",
            "- [ ] A qualified person who is neither the author nor the reviewer of the draft checks EVERY statutory value in every file",
            "      against the primary source (the statute or the authority's published guidance), and records the source in",
            "      `credit.statutory_citation` and each year's `_year_provenance.source`.",
            "- [ ] Only then remove the `_prototype_verify` flags they confirmed. Do not add `_verified` to a pack from this bundle.", "",
            "## 2. Put the files in the repository",
        };
        lines.AddRange(files.Where(f => f.StartsWith("rules/", StringComparison.Ordinal)).Select(f => $"- [ ] `{f}` -> `backend/{f}`"));
        lines.AddRange([
            "- [ ] Add the entry in `registry-patch.json` to `backend/rules/registry/programs.json` (lifecycle stays `described`; `calculable` is",
            "      derived from authored year packs and is never typed).", "",
            "## 3. Tests to add (customer-neutral, fictional or published values only)",
            $"- [ ] `backend/tests/test_{draft.ProposedCode.ToLowerInvariant()}_pack.py`: `validate_all()` reports no error for `{packFile}` and its years.",
            "- [ ] A pricing test at hand-computed inputs taken from the cited source (not from this tool's output) for each of: "
                + (draft.Years.Count > 0 ? string.Join(", ", draft.Years.Keys.Order(PyStrComparer)) : "each authored year") + ".",
            "- [ ] The program appears in `GET /api/v2/programs` as calculable for exactly its authored years, and is selectable in the",
            "      run dialog and the engagement controls with no frontend change.", "",
            "## 4. Changelog (same commit)", Changelog(draft), "",
            "## 5. Gates and deploy",
            "- [ ] `python scripts/validate-rule-pack.py`, the backend fast gate, the full backend suite, the frontend tests and build.",
            "- [ ] Commit, review and deploy the normal way (`azd up`). There is no database switch and no runtime toggle: the program becomes",
            "      calculable when the deployed rules folder holds its year packs.", "",
            "Year packs in this bundle: " + (yearFiles.Length > 0 ? string.Join(", ", yearFiles) : "none (the program will be described, not calculable)") + ".", "",
        ]);
        return string.Join("\n", lines);
    }

    private static IComparer<string> PyStrComparer => TaxCredit.Domain.Numerics.PyStr.Comparer;
}
