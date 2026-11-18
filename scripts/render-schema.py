"""Print a shipped SQL file (DDL, migration, grants) rendered under a data map's names.

    python scripts/render-schema.py docs/data/schema/tcc-schema.fabric.sql --map my-map.json > my-schema.sql

With no `--map` (or the shipped map) the output equals the input byte for byte. Nothing is executed:
run the output with `scripts/run-sql.py` or your own tool. The shipped files stay as they are so the
migration hashes recorded in `schema_migration` remain valid.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from data_map import default_map, load  # noqa: E402
from data_map_render import render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--map", dest="map_file", help="a complete data map file (default: the shipped map)")
    args = p.parse_args(argv)
    target = load(args.map_file) if args.map_file else default_map()
    sys.stdout.write(render(args.file.read_text(encoding="utf-8"), target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
