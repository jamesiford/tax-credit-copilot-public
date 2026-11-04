#!/usr/bin/env python3
"""Copy the shared, framework-free modules into the orchestrator, verbatim. [CH-08]

The orchestrator is a separate deployable (a Foundry hosted agent) and must not import
`backend/`. What it shares with the platform is the catalog, the envelope, the numeric
guard, the composer, the formatter and the model-access layer. Those modules are
standard-library only by rule, so they are COPIED rather than reimplemented: the guard
that checks a figure in the portal is byte-for-byte the guard that checks it in Teams.

The set is computed, not listed: start from SEEDS and follow imports. The copy fails if
the closure reaches a layer it may not (anything outside `application`, `domain` and
`infrastructure.ai`) or a third-party package outside the allow-list. Output goes to
`channel_orchestrator/app/vendor/tcc_shared/` with a SHA-256 manifest; the directory is
gitignored and the script is idempotent. `--check` verifies the copy still matches the
source and exits 1 on drift.

    python scripts/vendor-orchestrator.py            # write
    python scripts/vendor-orchestrator.py --check    # verify
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TARGET = ROOT / "channel_orchestrator" / "app" / "vendor" / "tcc_shared"

SEEDS = (
    "application.composer", "application.numeric_guard", "application.output_policy",
    "application.capabilities.catalog", "application.capabilities.envelope", "application.capabilities.format",
    "application.capabilities.lanes",
    "application.chat_scope", "application.chat_keywords",
    "application.ai.settings", "application.ai.egress", "application.ai.gateway_settings",
    "application.ai.safety.injection", "application.ai.safety.untrusted",
    "application.knowledge", "application.knowledge_settings",
    "domain.ai",
    "infrastructure.ai.openai_compatible", "infrastructure.ai.auth",
)
DATA_FILES = ("agents/prompts/channel_narrator.md",)

#: Repo layers the orchestrator may copy from.
ALLOWED_PREFIXES = ("application", "domain", "infrastructure.ai")
#: A package whose `__init__` must exist for an allowed child to import (it holds only a docstring).
PARENT_PACKAGES = frozenset({"infrastructure"})
LOCAL_ROOTS = frozenset({"application", "domain", "infrastructure", "api", "agents", "tools", "data", "config", "channel"})
#: Third-party packages, and only inside the model-access adapters.
THIRD_PARTY_FOR = {"infrastructure.ai": frozenset({"httpx", "azure"})}


class VendorError(Exception):
    """The closure leaves the allowed layers, or needs a package it may not."""


def module_path(name: str) -> Path | None:
    base = BACKEND / name.replace(".", "/")
    if base.with_suffix(".py").exists():
        return base.with_suffix(".py")
    init = base / "__init__.py"
    return init if init.exists() else None


def imported_names(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
            names += [f"{node.module}.{alias.name}" for alias in node.names]
    return names


def _third_party_ok(module: str, top: str) -> bool:
    return any(module.startswith(prefix) and top in allowed for prefix, allowed in THIRD_PARTY_FOR.items())


def _parents(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def closure(seeds: tuple[str, ...] = SEEDS) -> dict[str, Path]:
    """Every local module reachable from `seeds`, with its parents' `__init__`, or `VendorError`."""
    found: dict[str, Path] = {}
    stack = list(seeds)
    while stack:
        name = stack.pop()
        if name in found:
            continue
        path = module_path(name)
        if path is None:
            top = name.split(".")[0]
            if top in LOCAL_ROOTS:
                continue  # `from pkg.mod import attribute`: the attribute is not a module
            continue
        if not name.startswith(ALLOWED_PREFIXES) and name not in PARENT_PACKAGES:
            raise VendorError(f"{name} is outside the layers the orchestrator may copy ({ALLOWED_PREFIXES})")
        found[name] = path
        stack += _parents(name)
        for imported in imported_names(path):
            top = imported.split(".")[0]
            if top in LOCAL_ROOTS or module_path(imported):
                stack.append(imported)
            elif top not in sys.stdlib_module_names and top != "__future__" and not _third_party_ok(name, top):
                raise VendorError(f"{name} imports {imported!r}: a third-party package outside the allow-list")
    return found


def files_to_copy() -> dict[str, Path]:
    """Relative target path -> source, for modules and data files."""
    files = {str(path.relative_to(BACKEND)).replace("\\", "/"): path for path in closure().values()}
    for relative in DATA_FILES:
        source = BACKEND / relative
        if not source.exists():
            raise VendorError(f"data file {relative} does not exist")
        files[relative] = source
    return dict(sorted(files.items()))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_of(files: dict[str, Path]) -> dict[str, str]:
    return {relative: digest(source) for relative, source in files.items()}


def write() -> dict[str, str]:
    files = files_to_copy()
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for relative, source in files.items():
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    manifest = manifest_of(files)
    (TARGET / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def check() -> list[str]:
    """What differs between the copy and the source, as sentences. Empty when they agree."""
    manifest_file = TARGET / "MANIFEST.json"
    if not manifest_file.exists():
        return ["the vendored copy does not exist; run scripts/vendor-orchestrator.py"]
    recorded = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected = manifest_of(files_to_copy())
    problems = [f"{p} is not in the copy" for p in sorted(set(expected) - set(recorded))]
    problems += [f"{p} is in the copy but no longer needed" for p in sorted(set(recorded) - set(expected))]
    for relative in sorted(set(expected) & set(recorded)):
        copied = TARGET / relative
        if not copied.exists() or digest(copied) != expected[relative]:
            problems.append(f"{relative} differs from its source")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the copy instead of writing it")
    args = parser.parse_args()
    try:
        if args.check:
            problems = check()
            print("\n".join(problems) if problems else "vendored copy matches the source")
            return 1 if problems else 0
        manifest = write()
    except VendorError as exc:
        print(f"vendor-orchestrator: {exc}", file=sys.stderr)
        return 2
    print(f"vendored {len(manifest)} files into {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
