"""Zip an App Service package, honouring the service's `.webappignore`. [HOST-6]

    python scripts/package-app.py backend  out/api.zip
    python scripts/package-app.py frontend out/web.zip

The same exclusions azd applies, so a CI deploy can never ship what an `azd up`
would not: local `.env` files, the confidential reference payroll, local
operational stores. Patterns use a gitignore subset: `dir/` excludes a
directory anywhere, `a/b/` a directory at that path, `*.ext` and plain names
match a file name anywhere, and a path containing `/` matches from the root.
"""
from __future__ import annotations

import fnmatch
import sys
import zipfile
from pathlib import Path, PurePosixPath

#: Always excluded, whatever the ignore file says.
ALWAYS = (".git/", "__pycache__/", ".venv/", "node_modules/")


def load_patterns(root: Path) -> list[str]:
    ignore = root / ".webappignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.exists() else []
    patterns = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return [*ALWAYS, *patterns, ".webappignore"]


def excluded(relative: PurePosixPath, patterns: list[str]) -> bool:
    parts = relative.parts
    for pattern in patterns:
        if pattern.endswith("/"):
            directory = pattern.rstrip("/")
            if "/" in directory:
                if relative.as_posix().startswith(directory + "/"):
                    return True
            elif any(fnmatch.fnmatch(part, directory) for part in parts[:-1]):
                return True
        elif "/" in pattern:
            if fnmatch.fnmatch(relative.as_posix(), pattern.lstrip("/")):
                return True
        elif fnmatch.fnmatch(parts[-1], pattern):
            return True
    return False


def package(root: Path, destination: Path) -> list[str]:
    patterns = load_patterns(root)
    included: list[str] = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if excluded(relative, patterns):
                continue
            archive.write(path, relative.as_posix())
            included.append(relative.as_posix())
    return included


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    root, destination = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    files = package(root, destination)
    print(f"{destination}: {len(files)} files from {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
