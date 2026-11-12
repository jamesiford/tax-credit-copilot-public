"""Check, step by step, that this machine can read the lakehouse over OneLake. Operator tool.

    python scripts/check-onelake-access.py                 # uses backend/.env and the environment
    python scripts/check-onelake-access.py --table Account # which small table to open (default Account)

Prints the host it will call, whether that name resolves to a private address, whether a storage
token can be acquired (never shown), and the Delta version and file count of one small table, or
the precise error and what it usually means. Exit code 0 only when every step passed.
"""
from __future__ import annotations

import argparse
import sys

from sql_common import BACKEND, load_env

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", default="Account", help="logical table to open (default: Account)")
    args = parser.parse_args(argv)
    load_env()

    from config import get_settings
    from data.source import onelake
    from data.source.from_fabric import FabricLakehouseReader
    from data.source.onelake_diagnostics import check_dns, check_table, check_token, target_host

    source = get_settings().data_source
    reader = FabricLakehouseReader()
    print(f"data source       : {source.data_source}")
    print(f"workspace         : {reader.workspace or '(FABRIC_WORKSPACE not set)'}")
    print(f"lakehouse         : {reader.lakehouse or '(FABRIC_LAKEHOUSE not set)'}  path style: {source.onelake_path_style}")
    print(f"schema            : {reader.schema or '(none: lakehouse is not schema-enabled)'}")
    print(f"physical table    : {onelake.physical_table(args.table)}")
    print(f"endpoint          : {source.onelake_endpoint or 'default (public OneLake host)'}")
    print(f"host it will call : {target_host()}")
    if not reader.is_configured():
        print(f"\nFAIL config: set {' and '.join(reader.missing_settings())}.")
        return 2

    print(f"uri               : {onelake.table_uri(args.table, workspace=reader.workspace, lakehouse=reader.lakehouse, schema=reader.schema)}\n")
    steps = [check_dns(target_host()), check_token()]
    if all(step.ok for step in steps):
        steps.append(check_table(lambda: _open(reader, args.table), args.table))
    for step in steps:
        print(f"{'ok  ' if step.ok else 'FAIL'} {step.name}: {step.detail}")
        if step.hint and not step.ok:
            print(f"     what it usually means: {step.hint}")
    return 0 if all(step.ok for step in steps) else 1


def _open(reader, table: str) -> dict:
    return reader.table_lineage(table) or {}


if __name__ == "__main__":
    sys.exit(main())
