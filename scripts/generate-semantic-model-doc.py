"""Regenerate `docs/data/SEMANTIC-MODEL.md` from the semantic model. [CH-16a]

    python scripts/generate-semantic-model-doc.py          # write the page
    python scripts/generate-semantic-model-doc.py --check  # exit 1 if it is out of date

The page is derived, never edited: `backend/tests/test_semantic_model_doc.py` runs the
same comparison, so a change to the model that forgets the page fails the build.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from application.data.model_doc import render_markdown  # noqa: E402
from application.data.semantic_model import default_model  # noqa: E402

PAGE = ROOT / "docs" / "data" / "SEMANTIC-MODEL.md"


def main(argv: list[str]) -> int:
    """Write the page, or with `--check` say whether it is current."""
    text = render_markdown(default_model())
    if "--check" in argv:
        current = PAGE.read_text(encoding="utf-8") if PAGE.is_file() else ""
        if current != text:
            print(f"{PAGE} is out of date; run scripts/generate-semantic-model-doc.py")
            return 1
        return 0
    PAGE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
