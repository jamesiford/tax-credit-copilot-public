"""Stage C2.3: export each profile's starting state as DATA, so a different implementation can load the same seed.

    .\\contract\\py.ps1 -m contract.seed_export [--profile P1] [--check]

Writes `contract/seed/<profile>/`:
  source/<table>.jsonl.gz     the synthetic source tables as the source reader sees them (P1: the committed pay-period CSV; P2: the
                              Delta tables of the local lakehouse)
  gold/<table>.jsonl.gz       `tcc_gold.*` after the engine run, one JSON Lines file per table, values exactly as stored (SQLite)
  ops/<table>.jsonl.gz        `tcc_ops.run_manifest` and the operational tables the engine run wrote (claims, ...)
  manifest.json               row counts, columns, SHA-256 of every file, and the API-vs-seed cross-checks (gate G2)

Files are gzip with a zero mtime so the export is byte-reproducible.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED = ROOT / "contract" / "seed"


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    from contract import jsontext  # noqa: F401 - values are plain; Decimals/dates are made text below

    out = io.StringIO()
    for row in rows:
        out.write(json.dumps({k: _plain(v) for k, v in row.items()}, ensure_ascii=False, separators=(",", ":")) + "\n")
    return out.getvalue().encode("utf-8")


def _plain(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_py"):
        return _plain(value.as_py())
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if hasattr(value, "quantize"):  # Decimal
        return str(value)
    return value


def _gz(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as f:
        f.write(data)
    return buf.getvalue()


def _sqlite_tables(conn: sqlite3.Connection, schema: str) -> dict[str, tuple[list[str], list[dict[str, Any]]]]:
    out = {}
    names = [r[0] for r in conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for name in names:
        cur = conn.execute(f"SELECT * FROM {schema}.{name}")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        out[name] = (cols, rows)
    return out


async def _api_checks(world: Any) -> dict[str, Any]:
    """Gate G2: what the API serves agrees with the seed rows."""
    checks: dict[str, Any] = {}
    async with world.client() as http:
        scope = (await http.get("/api/scope")).json()
        portfolio = (await http.get("/api/v2/portfolio", params={"limit": 1000})).json()
        checks["api_scope_clients"] = len(scope["clients"])
        checks["api_portfolio_cells"] = portfolio["total"]
        per_client = {}
        for c in scope["clients"]:
            cid = c["account_id"]
            r = (await http.get("/api/eligibility/2025", params={"state": "GA", "account_id": cid, "limit": 1})).json()
            per_client[str(cid)] = {"employees_evaluated": r.get("employees_evaluated"), "min_max_eligible": r.get("min_max_eligible"), "pay_period_eligible": r.get("pay_period_eligible")}
        checks["api_eligibility_by_client"] = per_client
    return checks


def export(profile: str, out_dir: Path) -> dict[str, Any]:
    from contract.harness import world as w

    built = w.build(profile)
    files: dict[str, bytes] = {}
    manifest: dict[str, Any] = {"profile": profile, "notes": built.notes, "tables": {}}

    def put(kind: str, name: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
        data = _gz(_jsonl(rows))
        rel = f"{kind}/{name}.jsonl.gz"
        files[rel] = data
        manifest["tables"][rel] = {"rows": len(rows), "columns": columns, "sha256": hashlib.sha256(data).hexdigest()}

    if profile == "P1":
        path = ROOT / "backend" / "data" / "payroll_pay_periods.csv"
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            put("source", "pay_periods", list(reader.fieldnames or []), rows)
        manifest["source_origin"] = "backend/data/payroll_pay_periods.csv (committed synthetic fixture), DATA_SOURCE=csv, account 1001"
    else:
        from data.source.to_delta import TABLE_SPECS, _to_arrow
        from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset

        datasets = [build_synthetic_dataset(s) for s in SYNTHETIC_CLIENTS]
        import pyarrow as pa

        for table in TABLE_SPECS:
            parts = [_to_arrow(ds, table) for ds in datasets]
            combined = pa.concat_tables(parts) if len(parts) > 1 else parts[0]
            cols = combined.column_names
            put("source", table, cols, [{c: row[c] for c in cols} for row in combined.to_pylist()])
        manifest["source_origin"] = "data.source.synth.SYNTHETIC_CLIENTS via data.source.to_delta._to_arrow (logical source tables, as the source reader maps them)"

    conn = built.warehouse.connection.raw
    for schema, kind in (("tcc_gold", "gold"), ("tcc_ops", "ops")):
        for name, (cols, rows) in _sqlite_tables(conn, schema).items():
            put(kind, name, cols, rows)
    op = sqlite3.connect(str(Path(__import__("os").environ["OPERATIONAL_DB"])))
    for name in [r[0] for r in op.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]:
        cur = op.execute(f"SELECT * FROM {name}")
        cols = [d[0] for d in cur.description]
        put("operational", name, cols, [dict(zip(cols, r)) for r in cur.fetchall()])
    op.close()
    manifest["api_checks"] = asyncio.run(_api_checks(built))
    mismatches = []
    gold = {k.split("/")[1].split(".")[0]: v["rows"] for k, v in manifest["tables"].items() if k.startswith("gold/")}
    ee = {}
    for cid, got in manifest["api_checks"]["api_eligibility_by_client"].items():
        cur = conn.execute("SELECT COUNT(DISTINCT record_token) FROM tcc_gold.employee_eligibility WHERE client_id=? AND tax_year=2025 AND method='min_max'", (int(cid),))
        seed_n = cur.fetchone()[0]
        ee[cid] = seed_n
        if got["employees_evaluated"] is not None and got["employees_evaluated"] != seed_n:
            mismatches.append({"client": cid, "api": got["employees_evaluated"], "seed_distinct_tokens_min_max": seed_n})
    manifest["seed_employee_rows_min_max_2025"] = ee
    manifest["g2_mismatches"] = mismatches
    manifest["gold_row_counts"] = gold
    for rel, data in files.items():
        target = out_dir / profile / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out_dir / profile / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["P1", "P2"], required=True)
    parser.add_argument("--out", default=str(SEED))
    args = parser.parse_args()
    from contract.harness import hermetic

    hermetic.apply()
    manifest = export(args.profile, Path(args.out))
    print(json.dumps({"profile": args.profile, "tables": len(manifest["tables"]), "rows": sum(t["rows"] for t in manifest["tables"].values()),
                      "g2_mismatches": manifest["g2_mismatches"]}))
    return 1 if manifest["g2_mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
