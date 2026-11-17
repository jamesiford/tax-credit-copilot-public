"""Publish from the pinned SDK directory, then add exact product resources and hashes."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from stage import DEPLOY, ROOT, SERVICES, context, reset_directory, resources, stamp


def publish(service: str, output: Path, runtime: str | None = None, source: Path = ROOT) -> Path:
    version = subprocess.run(
        ["dotnet", "--version"], cwd=source / "dotnet", capture_output=True, text=True, check=True
    ).stdout.strip()
    if version != "10.0.404":
        raise RuntimeError("SDK 10.0.404 is required; run from dotnet.")
    name = "TaxCredit." + SERVICES[service]
    command = ["dotnet", "publish", str(source / "dotnet" / "src" / name / (name + ".csproj")),
               "-c", "Release", "--self-contained", "false", "-o", str(output),
               "--nologo", "-v:q", "-m:1", "-nr:false",
               "-p:ContinuousIntegrationBuild=true", "-p:UseAppHost=false",
               "-p:RestorePackagesWithLockFile=true", "-p:RestoreLockedMode=true",
               "-p:RuntimeIdentifiers=linux-x64"]
    if runtime:
        command.extend(["-r", runtime])
    subprocess.run(command, cwd=source / "dotnet", check=True)
    if service != "orchestrator":
        resources(output / "resources")
    subprocess.run(
        ["dotnet", "publish", str(DEPLOY / "telemetry" / "Hook" / "TaxCredit.Deployment.Telemetry.csproj"),
         "-c", "Release", "-o", str(output / "telemetry"), "--nologo", "-v:q"],
        cwd=ROOT / "dotnet", check=True
    )
    for script in ("start-orchestrator.sh", "probe.sh"):
        shutil.copyfile(DEPLOY / "containers" / script, output / script)
    manifest = stamp(output, service)
    print(f"{service}: SDK {version}; {len(manifest['files'])} hashed files.")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=[*SERVICES, "all"], default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--runtime")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("CPython 3.12 is required.")
    if args.output and args.service == "all":
        parser.error("--output requires one service.")
    source = context()
    for service in SERVICES if args.service == "all" else [args.service]:
        target = (args.output or DEPLOY / ".artifacts" / "publish" / service).resolve()
        if args.output:
            # azd owns its temporary PublishDir; do not delete or enumerate its parent.
            target.mkdir(parents=True, exist_ok=True)
            if any(target.iterdir()):
                parser.error("--output must be an empty publication directory.")
        else:
            reset_directory(target, DEPLOY / ".artifacts" / "publish")
        publish(service, target, args.runtime, source)


if __name__ == "__main__":
    main()
