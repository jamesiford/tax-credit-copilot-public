"""Check or refresh agents/prompts/manifest.json. [AI-06]

    python scripts/prompt-manifest.py            # check (exit 1 on any disagreement)
    python scripts/prompt-manifest.py --refresh  # record the current versions

`--refresh` never rewrites a version that is already recorded: bump `version` in the
prompt's front matter (and add its changelog line) first. See
`backend/infrastructure/ai/prompt_manifest.py` for the rule and the reason.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from infrastructure.ai.prompt_manifest import ManifestError, check, load_manifest, refresh, save_manifest  # noqa: E402
from infrastructure.ai.prompts_fs import FilePromptStore  # noqa: E402


def main(argv: list[str]) -> int:
    store, manifest = FilePromptStore(), load_manifest()
    if "--refresh" in argv:
        try:
            save_manifest(refresh(store, manifest))
        except ManifestError as exc:
            print(f"refused: {exc}")
            return 1
        print(f"manifest recorded for {len(store.names())} prompts")
        return 0
    problems = check(store, manifest)
    for problem in problems:
        print(problem)
    print("prompts and manifest agree" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
