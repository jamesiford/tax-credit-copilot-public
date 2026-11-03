"""Regenerate docs/m365-channel/evidence/publish-whatif.txt: the script's -WhatIf output against a fake `az`.

    cd backend ; ..\\.venv\\Scripts\\python.exe tools_dev\\... (run as: python tests/make_publish_whatif.py)

Every identifier in the transcript is a placeholder from tests/publish_shim.py.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import publish_shim as shim  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "docs" / "m365-channel" / "evidence" / "publish-whatif.txt"


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        fake = shim.install(Path(folder))
        arguments = [*shim.required_arguments(), "-AppVersion", "1.0.0", "-PublishScope", "Shared", "-OutputDir", "./publish-output", "-WhatIf"]
        done = subprocess.run(
            [shim.PWSH, "-NoProfile", "-NonInteractive", "-File", str(REPO / "scripts" / "publish-m365.ps1"), *arguments],
            capture_output=True, text=True, env=fake.environment(), cwd=folder, timeout=180,
        )
        shown = " ".join(f'"{a}"' if " " in a else a for a in arguments)
        header = (
            "# scripts/publish-m365.ps1 -WhatIf, against a fake `az` (backend/tests/publish_shim.py).\n"
            "# Every identifier below is a placeholder. The agent was read; nothing was created, changed or published.\n"
            f"# pwsh -File scripts/publish-m365.ps1 {shown}\n"
            f"# exit code: {done.returncode}\n\n"
        )
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(header + done.stdout + done.stderr, encoding="utf-8")
        print(f"wrote {TARGET} (exit {done.returncode}, {len(done.stdout.splitlines())} lines)")


if __name__ == "__main__":
    main()
