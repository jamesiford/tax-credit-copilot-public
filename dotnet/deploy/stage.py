"""Stage tracked, allowlisted product inputs without including the working environment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent.parent
SERVICES = {"api": "Api", "worker": "Worker", "gateway": "Gateway", "orchestrator": "Orchestrator"}
RESOURCE_PREFIXES = ("backend/rules/", "backend/data/rules_ingested/", "docs/data/schema/")
RESOURCE_FILES = {"backend/data/payroll.csv", "backend/data/payroll_pay_periods.csv"}
BUILD_FILES = {"backend/data/source/mapping/default.json"}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return result.stdout.decode("utf-8").rstrip("\0").split("\0")


def is_resource(name: str) -> bool:
    if any(part.startswith(".") or part in {"bin", "obj"} for part in name.split("/")):
        return False
    return (name.startswith(RESOURCE_PREFIXES) or name in RESOURCE_FILES) and (
        Path(name).suffix in {".json", ".sql", ".csv"}
    )


def is_source(name: str) -> bool:
    if name.startswith("dotnet/src/TaxCredit.AppHost/") or any(
        part.startswith(".env") or part in {"bin", "obj"} for part in name.split("/")
    ):
        return False
    return (
        name.startswith("dotnet/src/")
        or name in {"dotnet/global.json", "dotnet/Directory.Build.props",
                    "dotnet/Directory.Build.targets", "dotnet/Directory.Packages.props",
                    "dotnet/NuGet.Config", "dotnet/nuget.config", "dotnet/.editorconfig"}
        or name in BUILD_FILES
    ) and Path(name).suffix in {".cs", ".csproj", ".props", ".targets", ".json", ".gz", ".resx", ".config", ""}


def reset_directory(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != parent.resolve() or path.is_symlink():
        raise ValueError("Staging destination must be a named direct child of its owned parent.")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def copy_tracked(names: list[str], destination: Path) -> None:
    for name in names:
        source = ROOT.joinpath(*name.split("/"))
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError("Resource links are not accepted.")
        target = destination.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def stamp(directory: Path, service: str) -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    files = [
        {"path": path.relative_to(directory).as_posix(),
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "artifact-manifest.json"
    ]
    manifest = {"schema": 1, "service": service, "commit": commit, "files": files}
    (directory / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def resources(destination: Path) -> None:
    copy_tracked([name for name in tracked_files() if is_resource(name)], destination)
    required = ("backend/rules/registry/programs.json",
                "backend/rules/schema/rule-pack.schema.json",
                "backend/data/payroll.csv", "docs/data/schema/tcc-schema.sqlserver.sql")
    if any(not destination.joinpath(*name.split("/")).is_file() for name in required):
        raise ValueError("A required authored runtime resource is absent.")


def context() -> Path:
    target = DEPLOY / ".staging" / "context"
    reset_directory(target, DEPLOY / ".staging")
    copy_tracked([name for name in tracked_files() if is_source(name)], target)
    for lock in (DEPLOY / "locks").glob("*/packages.lock.json"):
        project = target / "dotnet" / "src" / lock.parent.name
        if not project.is_dir():
            raise ValueError("Lock names an absent staged project.")
        shutil.copyfile(lock, project / "packages.lock.json")
    resources(target / "resources")
    shutil.copytree(DEPLOY / "containers", target / "containers")
    hook = target / "telemetry"
    hook.mkdir()
    shutil.copyfile(DEPLOY / "telemetry" / "Directory.Build.props", hook / "Directory.Build.props")
    for source in (DEPLOY / "telemetry" / "Hook").rglob("*"):
        if source.is_file() and source.suffix in {".cs", ".csproj"}:
            relative = source.relative_to(DEPLOY / "telemetry")
            destination = hook / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    (target / "packages").mkdir()
    (target / "packages" / ".keep").write_text("", encoding="utf-8")
    # This file is authored here, not inherited from the repository root.
    (target / ".dockerignore").write_text(
        "**/.env*\n**/bin\n**/obj\n**/*.db*\n**/*.pfx\n**/*.pem\n.git\n", encoding="utf-8"
    )
    stamp(target, "build-context")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", action="store_true", required=True)
    parser.parse_args()
    output = context()
    print(f"Bounded context ready: {len(list(output.rglob('*')))} entries.")


if __name__ == "__main__":
    main()
