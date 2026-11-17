"""Inventory register history without rewriting any producer scope or waiver."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

from admission import HERE, ROOT

DIRECTORY = "dotnet/docs/improvements"
WAVES = {"skeleton": "W1a", "W1-skeleton": "W1a", "persistence": "W1b",
         "sources_auth_ai": "W1b", "composition": "W1b", "integrate-W1": "W1b",
         "gateway": "W3", "orchestrator": "W3", "integrate-W3": "W3", "integration": "W4"}
EFFECTS = {"defect_fix": "behavioral-defect-fix", "error_text": "error-wording",
           "wire_incidental": "wire-incidental", "framework_default": "framework-default"}


def git(*arguments: str) -> str:
    return subprocess.run(["git", "--no-pager", *arguments], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def history() -> tuple[list[dict], dict]:
    revisions = git("log", "--format=%H", "--", DIRECTORY).splitlines()
    blobs, files = {}, defaultdict(set)
    for revision in revisions:
        for line in git("ls-tree", "-r", revision, "--", DIRECTORY).splitlines():
            spec, path = line.split("\t", 1)
            if not path.endswith(".json"):
                continue
            blob = spec.split()[-1]
            files[path].add(blob)
            blobs.setdefault((path, blob), revision)
    versions = []
    for (path, blob), revision in blobs.items():
        document = json.loads(git("cat-file", "blob", blob))
        versions.append({"register": path, "revision": revision[:8],
                         "entries": document["improvements"], "current": False})
    for path in sorted((ROOT / "dotnet" / "docs" / "improvements").glob("*.json")):
        versions.append({"register": path.relative_to(ROOT).as_posix(), "revision": "W4-worktree",
                         "entries": json.loads(path.read_text(encoding="utf-8-sig"))["improvements"],
                         "current": True})
    return versions, files


def consolidate(versions: list[dict], board: dict) -> list:
    unique = {}
    for version in versions:
        for entry in version["entries"]:
            key = json.dumps(entry, sort_keys=True)
            item = unique.setdefault(key, {"entry": entry, "sources": [], "current": False})
            item["current"] |= version["current"]
            item["sources"].append({key: version[key] for key in ("register", "revision", "current")})
    current_ids = {item["entry"]["id"] for item in unique.values() if item["current"]}
    results = []
    for ordinal, item in enumerate(unique.values(), 1):
        entry = item.pop("entry")
        flags = []
        if not entry.get("path_prefix") or not entry.get("categories"):
            flags.append("broad-scope-owner-review")
        if entry.get("case", "").startswith("unrecorded."):
            flags.append("not-a-recorded-case")
        if entry["kind"] not in EFFECTS:
            flags.append("unsupported-current-kind")
        matched = board["register_match_fields"].get(entry["id"], 0) if item["current"] else 0
        if item["current"] and not matched:
            flags.append("not-hit-in-fresh-sample")
        state = ("current-deliberate-difference" if item["current"] else
                 "historical-superseded-scope" if entry["id"] in current_ids else "historical-withdrawn")
        sources = item["sources"]
        results.append({"id": f"REG-{ordinal:03}", "source_id": entry["id"], "state": state,
                        "waves": sorted({WAVES.get(Path(source["register"]).stem, "W2") for source in sources}),
                        "sources": sources, "route": entry["route"], "case": entry.get("case"),
                        "path": entry.get("path_prefix"), "categories": entry.get("categories"),
                        "kind": entry["kind"], "finding": entry.get("finding", ""), "reason": entry["reason"],
                        "effect_class": EFFECTS.get(entry["kind"], "historical-unclassified"),
                        "fresh_matching_fields": matched,
                        "fresh_accepted_fields": board["register_accepted_fields"].get(entry["id"], 0) if item["current"] else 0,
                        "flags": flags, "evidence": [source["register"] + "@" + source["revision"] for source in sources],
                        "reproduction": "Fresh hermetic baseline; select source route/case/path. Unrecorded cases require named producer tests.",
                        "disposition": "Document only; preserve exact source scope. Historical variants cannot waive current failures.",
                        "owner_review": "pending-cutover-review" if item["current"] else "not-current-waiver-eligible"})
    return results


def inventory(versions: list[dict], files: dict) -> list:
    grouped = defaultdict(list)
    for version in versions:
        grouped[version["register"]].append(version)
    result = []
    for register, rows in sorted(grouped.items()):
        current = next((row for row in rows if row["current"]), None)
        path = ROOT / Path(register)
        result.append({"register": register, "current": current is not None,
                       "current_entries": len(current["entries"]) if current else 0,
                       "historical_blob_versions": len(files.get(register, [])),
                       "historical_empty_versions": sum(not row["entries"] and not row["current"] for row in rows),
                       "current_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if current else None})
    return result


def human(report: dict) -> str:
    lines = ["# Shadow deviations and decisions", "",
             "This is an inventory, **not cutover approval**. Complete reasons, exact source scopes, historical versions and field-level residuals are in [SHADOW-DEVIATIONS.json](SHADOW-DEVIATIONS.json). Raw payloads are absent.", "",
             "## Register inventory", "", "| Register | Current entries | Historical versions | Empty historical versions |",
             "|---|---:|---:|---:|"]
    for row in report["register_inventory"]:
        lines.append(f"| `{row['register']}` | {row['current_entries']} | {row['historical_blob_versions']} | {row['historical_empty_versions']} |")
    lines += ["", "Duplicate skeleton IDs/content are coalesced with both source files retained. Narrowed scopes remain separate historical variants; removed IDs are withdrawn, not current exceptions.", "",
              "## Current and historical differences", "",
              "| Source ID | State | Method/template | Case / path | Fresh matches / accepted | Scope review |",
              "|---|---|---|---|---:|---|"]
    for row in report["register_differences"]:
        scope = (row["case"] or "*") + " / " + (row["path"] or "*")
        flags = ", ".join(row["flags"]) or "exact source scope; owner pending"
        lines.append(f"| `{row['source_id']}` | {row['state']} | `{row['route']}` | `{scope}` | {row['fresh_matching_fields']} / {row['fresh_accepted_fields']} | {flags} |")
    lines += ["", "## Fresh unresolved cases", "",
              "Each row groups all retained failing fields for one synthetic recorded case. The machine register retains category, safe path template and original failure ordinal for reproduction. No register match is treated as approval.", "",
              "| Group | Scenario / case | Failing fields |", "|---|---|---:|"]
    cases = defaultdict(int)
    for row in report["unresolved_differences"]:
        cases[(row["group"], row["scenario"], row["case"])] += 1
    for (group, scenario, case), count in sorted(cases.items()):
        lines.append(f"| {group} | `{scenario}:{case}` | {count} |")
    lines += ["", "## Operational and policy decisions", ""]
    for row in report["decisions"]:
        lines += [f"### {row['id']} - {row['scope']}", "", row["reason"], "",
                  f"**Owner:** {row['owner']}. **Disposition:** {row['disposition']} "
                  f"**Review:** {'required' if row['review_required'] else 'resolved or evidence boundary'}.", "",
                  "Evidence: " + "; ".join("`" + path + "`" for path in row["evidence"]) + ".", ""]
    return "\n".join(lines)


def main() -> None:
    board = json.loads((ROOT / "dotnet" / "docs" / "integration-replay.json").read_text())
    versions, files = history()
    differences = consolidate(versions, board)
    unresolved = [{**row, "id": f"UNRES-{ordinal:04}", "wave": "W4-observed",
                   "register": None, "reason": "Not resolved by current global policy or exact register scope.",
                   "evidence": "integration-replay.json; fresh synthetic raw report and field ordinal",
                   "effect_class": "unresolved-producer-" + row["category"],
                   "reproduction": row["scenario"] + ":" + row["case"],
                   "disposition": "Producer repair or explicit owner decision; no observer rewrite.",
                   "owner_review": "required"}
                  for ordinal, row in enumerate(board["unresolved"], 1)]
    report = {"kind": "Complete producer-register history plus fresh unresolved and operational decisions",
              "product_revision": "006760b", "approval": "documentation is not cutover approval",
              "register_inventory": inventory(versions, files), "register_differences": differences,
              "unresolved_differences": unresolved,
              "decisions": json.loads((HERE / "operational-decisions.json").read_text())["decisions"]}
    (ROOT / "dotnet" / "docs" / "SHADOW-DEVIATIONS.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "dotnet" / "docs" / "SHADOW-DEVIATIONS.md").write_text(human(report) + "\n", encoding="utf-8")
    print(json.dumps({"registers": len(report["register_inventory"]), "unique_variants": len(differences),
                      "current": sum(row["state"] == "current-deliberate-difference" for row in differences),
                      "unresolved_fields": len(unresolved), "decisions": len(report["decisions"])}))


if __name__ == "__main__":
    main()
