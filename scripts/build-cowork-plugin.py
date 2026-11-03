"""Build the Copilot Cowork plugin package. [CH-10]

    python scripts/build-cowork-plugin.py --config overlays/<name>/cowork.json
    python scripts/build-cowork-plugin.py --config channels/cowork/config.example.json   # placeholders: a dry run
    python scripts/build-cowork-plugin.py --config ... --strict                           # refuse placeholders

Renders `manifest.json` from `channels/cowork/manifest.template.json`, draws the two PNG
icons, copies the skills, validates everything offline, and writes `dist/tcc-cowork-plugin.zip`
reproducibly. Prints the SHA-256 so the file that was reviewed is provably the file uploaded.

Exit codes: 0 built · 1 validation errors (nothing is written) · 2 bad configuration.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cowork_plugin.package import BuildError, build  # noqa: E402
from cowork_plugin.settings import ConfigError, load_settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, help="JSON file of deployment values (see channels/cowork/config.example.json)")
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="output folder (default: dist/, gitignored)")
    parser.add_argument("--strict", action="store_true", help="treat placeholder values as errors")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        result = build(settings, args.out, strict=args.strict)
    except ConfigError as exc:
        print(f"configuration: {exc}", file=sys.stderr)
        return 2
    except BuildError as exc:
        print("the package did not validate:", *(str(f) for f in exc.findings), sep="\n  ", file=sys.stderr)
        return 1
    for finding in result.findings:
        print(finding)
    print(f"app id    {settings.app_id}\nmanifest  {settings.manifest_version}\nfiles     {len(result.files)}")
    print(f"wrote     {result.zip_path}\nsha256    {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
