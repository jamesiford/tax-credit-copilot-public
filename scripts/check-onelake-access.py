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
    parser.add_argument("--probe-layout", action="store_true",
                        help="also try the other schema layout (a schema versus none) and say which one opens the table")
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
    if args.probe_layout and all(step.ok for step in steps[:2]):
        steps = steps[:2] + _probe(reader, args.table)
    for step in steps:
        print(f"{'ok  ' if step.ok else 'FAIL'} {step.name}: {step.detail}")
        if step.hint and not step.ok:
            print(f"     what it usually means: {step.hint}")
    return 0 if all(step.ok for step in steps) else 1


def _probe(reader, table: str) -> list:
    """Both schema layouts. Passes when either opens the table, and says which one to configure."""
    from data.source.from_fabric import FabricLakehouseReader
    from data.source.onelake_diagnostics import Step, probe_layout

    steps, winner = probe_layout(
        lambda schema: FabricLakehouseReader(workspace=reader.workspace, lakehouse=reader.lakehouse, schema=schema).table_lineage(table) or {},
        table, reader.schema,
    )
    if winner is None:
        return steps
    verdict = f"SOURCE_SCHEMA={winner}" if winner else "SOURCE_SCHEMA= (blank: not schema-enabled)"
    note = "that is what is configured" if winner == reader.schema else "THAT DIFFERS from what is configured"
    return [Step(s.name, True, s.detail if s.ok else f"did not open ({s.detail[:80]})") for s in steps] + [
        Step("layout verdict", True, f"{verdict}; {note}.")
    ]


def _open(reader, table: str) -> dict:
    return reader.table_lineage(table) or {}


if __name__ == "__main__":
    sys.exit(main())
