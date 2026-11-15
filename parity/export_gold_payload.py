"""Golden vectors for the run command's pure pipeline (stage CAP): payroll in, the exact payload the Gold writer receives out.

Runs the PRODUCTION ``handle_run_client_calculation`` (through the mediator, as the app does) with a CAPTURING writer installed through
``bootstrap.wiring``, exactly as ``backend/tests/test_run_client_calculation.py`` and ``data_engine_fixture.py`` do. Nothing in product code is changed;
what the exporter freezes, and only in this process, is recorded in the meta line (``freezes``):

* the clock: ``tools.gold_projection.utc_now`` (three readings per run: started, appended_at, completed) and ``application.open_year.today``;
* the run id: ``application.commands.run_client_calculation.uuid`` (``uuid4().hex`` = the first 32 hex digits of ``sha256("run:<name>")``);
* the commit: ``GIT_COMMIT`` (``code_commit`` is read from settings first, so ``git rev-parse`` is never reached);
* the environment: ``DATA_SOURCE=csv`` (the fixture source; a fiscal window is then an ASSUMED calendar year), ``DATA_CLASSIFICATION=synthetic``.

Line formats (JSONL, gzip, mtime 0):

* ``{"k":"meta",...}`` the freezes, every column list, the designation registry the run read, the assumption identities, the section-9 count.
* ``{"k":"call","fn":...}`` helper calls (``payload_helpers.py``): program defaults, payroll rows, fiscal source, fingerprint, statute resolution.
* ``{"k":"run","name":...}`` one run: arguments, the handler's result, the manifest row, every table as typed cells (``["dec","1.00"]``, ``["int",5]``,
  ``["str","x"]``, ``["date",iso]``, ``["dt",iso]``, ``["bool",b]``, ``["float",repr,bits]``, ``["null"]``) with the table's column list, its row count and an ordered SHA-256 over the rows' compact JSON (one line per row).

Subjects: the committed synthetic payroll (``backend/data/payroll_pay_periods.csv``) and every client of ``SYNTHETIC_CLIENTS``; ALL rows of all seven tables are kept
(about 5 MB gzipped, so no digest-only policy is needed). The synthetic clients' payroll, trimmed to the columns the pipeline reads, is the second golden
``gold_payload_input.jsonl.gz``. Claims the assessment records are captured without their volatile fields (``claim_id``, ``decided_at``, ``effective_*``).

Usage: python parity/export_gold_payload.py [--check] [--out DIR]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import struct
import sys
import types
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

FROZEN_COMMIT = "0123456789abcdef0123456789abcdef01234567"
FROZEN_TODAY = date(2026, 11, 15)
FROZEN_CLOCK = datetime(2026, 11, 15, 9, 30, 15)
os.environ.update({"DATA_SOURCE": "csv", "FIXTURE_ACCOUNT_ID": "1001", "DATA_CLASSIFICATION": "synthetic", "GIT_COMMIT": FROZEN_COMMIT})
os.environ.pop("ENVIRONMENT", None)

from bootstrap import wiring  # noqa: E402
import application.commands.run_client_calculation as rcc  # noqa: E402
import application.open_year as open_year  # noqa: E402
from tools import gold_projection as gp  # noqa: E402
import payload_helpers as ph  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "goldens"
TABLES = ("employee_period_fact", "employee_eligibility", "onezero_matrix", "unit_month_summary", "run_method_summary", "unit_year_master", "unit_credit_installment")
COLUMNS = {
    "employee_period_fact": gp.EMPLOYEE_PERIOD_FACT_COLUMNS, "employee_eligibility": gp.EMPLOYEE_ELIGIBILITY_COLUMNS, "onezero_matrix": gp.ONEZERO_MATRIX_COLUMNS,
    "unit_month_summary": gp.UNIT_MONTH_SUMMARY_COLUMNS, "run_method_summary": gp.RUN_METHOD_SUMMARY_COLUMNS, "unit_year_master": gp.UNIT_YEAR_MASTER_COLUMNS,
    "unit_credit_installment": gp.UNIT_CREDIT_INSTALLMENT_COLUMNS,
}
INPUT_COLUMNS = ("Tax_Year", "Employee_ID", "Worksite_ID", "Work_State", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Pay_Code", "Pay_Frequency", "Job_Title", "Hours_Worked", "Gross_Wages")
VOLATILE_CLAIM_FIELDS = {"claim_id", "decided_at", "effective_from", "effective_to"}


def dumps(x) -> str:
    return json.dumps(x, separators=(",", ":"), ensure_ascii=True)


def cell(v) -> list:
    """The typed, JSON-able view of one value (datetime before date: one subclasses the other; bool before int)."""
    if v is None:
        return ["null"]
    if isinstance(v, bool):
        return ["bool", v]
    if isinstance(v, int):
        return ["int", v]
    if isinstance(v, Decimal):
        return ["nan", str(v)] if v.is_nan() else ["dec", str(v)]
    if isinstance(v, str):
        return ["str", v]
    if isinstance(v, datetime):
        return ["dt", v.isoformat()]
    if isinstance(v, date):
        return ["date", v.isoformat()]
    if isinstance(v, float):
        return ["float", repr(v), format(struct.unpack(">Q", struct.pack(">d", v))[0], "016x")]
    if hasattr(v, "value"):
        return ["str", v.value]
    raise TypeError(f"no cell encoding for {type(v).__name__}")


class Capture:
    """The writer the run hands its payload to: keeps it, and returns the per-table counts a real writer returns."""

    def __init__(self) -> None:
        self.payload = None

    def write_run(self, payload: dict) -> dict:
        self.payload = payload
        return {table: len(rows) for table, rows in payload.items() if isinstance(rows, list)}

    def validate(self) -> list:
        return []


class Claims:
    """A claim repository that keeps what the assessment records; ``seed`` are claims a cell already holds (the run reads the current claim of a cell)."""

    def __init__(self, seed: list | None = None) -> None:
        self.recorded: list = []
        self.seed = {(c.client_id, c.program_code, c.tax_year): c for c in seed or []}

    def current(self, client_id, program_code, tax_year):
        return self.seed.get((client_id, program_code, tax_year))

    def record(self, claim):
        self.recorded.append(claim)
        return claim


class Overrides:
    """Saved base years (WI-21): ``{(client, program): {unit: year}}``; the run reads nothing else."""

    def __init__(self, saved: dict) -> None:
        self.saved = saved

    def base_years(self, client_id: int, program_code: str) -> dict:
        return dict(self.saved.get((client_id, program_code), {}))


class Frozen:
    """The one clock and id source of a run."""

    def __init__(self, name: str) -> None:
        self.name, self.reads = name, 0

    def utc_now(self) -> datetime:
        at = FROZEN_CLOCK + timedelta(seconds=self.reads)
        self.reads += 1
        return at

    def uuid4(self):
        return types.SimpleNamespace(hex=hashlib.sha256(("run:" + self.name).encode()).hexdigest()[:32])


def table_record(name: str, rows: list) -> dict:
    columns = list(COLUMNS[name])
    digest, out = hashlib.sha256(), []
    for row in rows:
        if len(row) != len(columns):
            raise SystemExit(f"{name}: a row has {len(row)} cells for {len(columns)} columns")
        cells = [cell(v) for v in row]
        digest.update((dumps(cells) + "\n").encode("ascii"))
        out.append(cells)
    return {"columns": columns, "n": len(rows), "digest": digest.hexdigest(), "rows": out}


def claim_tree(claim) -> list:
    import dataclasses

    return [[f.name, cell(getattr(claim, f.name))] for f in dataclasses.fields(claim) if f.name not in VOLATILE_CLAIM_FIELDS]


#: Claims a cell already holds, by run name: (client, program, year, status, identified_usd). Only a cell past `not_assessed` is refreshed rather than replaced.
SEEDS = {"csv-ty2025-existing-claim": [(1001, "GA_JTC", 2024, "proposed", "123"), (1001, "GA_JTC", 2025, "not_assessed", "0"), (1001, "GA_JTC", 2023, "declined", "5")]}


def seeded(name: str) -> list:
    from domain.claims import ClaimStatus, ProgramClaim, Provenance

    return [ProgramClaim(client_id=c, program_code=p, tax_year=y, status=ClaimStatus(s), provenance=Provenance.COMPUTED, identified_usd=Decimal(i), decided_by="analyst",
                         decline_reason="prefers R&D" if s == "declined" else None) for c, p, y, s, i in SEEDS.get(name, [])]


def execute(name: str, args: dict, overrides: dict | None = None) -> dict:
    """One production run of the command; the record holds its outcome (result or the exception's type and message)."""
    from application.commands.run_client_calculation import RunClientCalculationCommand

    frozen, writer, claims = Frozen(name), Capture(), Claims(seeded(name))
    rcc.uuid, gp.utc_now = types.SimpleNamespace(uuid4=frozen.uuid4), frozen.utc_now
    wiring.set_gold_writer(writer)
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(Overrides(overrides or {}))
    record = {"k": "run", "name": name, "args": dict(args), "overrides": [[c, p, sorted(m.items())] for (c, p), m in sorted((overrides or {}).items())], "seed_claims": [list(s) for s in SEEDS.get(name, [])]}
    try:
        result = wiring.get_mediator().send(RunClientCalculationCommand(**args))
    except Exception as e:  # the exception type and message are part of the contract
        record.update({"err": type(e).__name__, "msg": str(e)})
        return record
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(None)
        wiring.set_override_repository(None)
    p = writer.payload
    record["out"] = {
        "result": result, "client_id": p["client_id"], "program_code": p["program_code"], "run_id": p["run_id"], "run_completed_at": cell(p["run_completed_at"]),
        "manifest_columns": list(p["run_manifest_columns"]), "manifest": [cell(v) for v in p["run_manifest_row"]],
        "tables": {t: table_record(t, p[t]) for t in TABLES}, "claims": [claim_tree(c) for c in claims.recorded], "clock_reads": frozen.reads,
    }
    return record


def synthetic_rows() -> dict:
    from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
    from data.source.to_bcs import source_to_bcs_rows

    import logging
    logging.disable(logging.CRITICAL)
    try:
        return {spec.account_id: source_to_bcs_rows(build_synthetic_dataset(spec)) for spec in SYNTHETIC_CLIENTS}
    finally:
        logging.disable(logging.NOTSET)


def csv_rows() -> list:
    from infrastructure.payroll import pay_period_source

    return pay_period_source.load_pay_periods(1001)


def trimmed(rows: list) -> list:
    return [[r.get(c) for c in INPUT_COLUMNS] for r in rows]


def serve(rows_by_client: dict):
    """A multi-tenant payroll source for the run: the rows of the named client, none when no tenant is named (the lakehouse's contract)."""
    from infrastructure.payroll import pay_period_source

    def load(account_id=None):
        return list(rows_by_client.get(account_id, [])) if account_id is not None else []

    pay_period_source.load_pay_periods = load


def runs(synthetic: dict) -> list:
    """(name, args, overrides, source) for every subject."""
    out = [
        ("csv-ty2025-ga", {"client_id": 1001, "tax_year": 2025, "state": "GA", "actor": "tests"}, None, "csv"),
        ("csv-ty2024-program", {"client_id": 1001, "tax_year": 2024, "program_code": "GA_JTC", "actor": "operator"}, None, "csv"),
        ("csv-ty2026-derived-open", {"client_id": 1001, "tax_year": 2026, "assess_tax_years": (2025,)}, None, "csv"),
        ("csv-ty2025-saved-base-year", {"client_id": 1001, "tax_year": 2025, "state": "GA"}, {(1001, "GA_JTC"): {"GA_GA-001": 2025, "GA_GA-002": 2099, "GA_GA-003": 2024}}, "csv"),
        ("csv-ty2025-existing-claim", {"client_id": 1001, "tax_year": 2025, "state": "GA", "assess_tax_years": (2023, 2024, 2025)}, None, "csv"),
        ("csv-ty2018-unauthored", {"client_id": 1001, "tax_year": 2018, "state": "GA"}, None, "csv"),
        ("csv-unknown-client", {"client_id": 9999, "tax_year": 2025, "state": "GA"}, None, "csv"),
        ("csv-unknown-program", {"client_id": 1001, "tax_year": 2025, "program_code": "XX_NONE"}, None, "csv"),
        ("csv-federal-program", {"client_id": 1001, "tax_year": 2025, "program_code": "FEDERAL_WOTC_LITE"}, None, "csv"),
        ("csv-state-without-year-packs", {"client_id": 1001, "tax_year": 2025, "state": "TN"}, None, "csv"),
    ]
    for client in sorted(synthetic):
        out.append((f"synth-{client}-ty2025-derived", {"client_id": client, "tax_year": 2025, "actor": "sweep"}, None, client))
    out += [
        ("synth-2003-ty2026-ga", {"client_id": 2003, "tax_year": 2026, "state": "GA", "actor": "sweep"}, None, 2003),
        ("synth-2001-ty2023-ga-saved", {"client_id": 2001, "tax_year": 2023, "state": "GA"}, {(2001, "GA_JTC"): {"GA_GA-013": 2021, "GA_GA-001": 2030}}, 2001),
        ("synth-2001-ty2023-sc", {"client_id": 2001, "tax_year": 2023, "state": "SC"}, None, 2001),
        ("synth-2002-ty2023-tn", {"client_id": 2002, "tax_year": 2023, "state": "TN"}, None, 2002),
        ("synth-2004-ty2022-ga", {"client_id": 2004, "tax_year": 2022, "state": "GA", "assess_tax_years": (2021, 2022)}, None, 2004),
    ]
    return out


def build() -> tuple[bytes, bytes]:
    from data.designations import _DESIGNATION_HISTORY, _SOURCE_DESIGNATIONS, _SYNTHETIC_GA_DEFAULT
    from application.gold_ports import section_9_query_count
    from domain.warehouse import RUN_MANIFEST_COLUMNS
    from infrastructure.payroll import pay_period_source as pps

    open_year.today = lambda: FROZEN_TODAY
    real_loader = pps.load_pay_periods
    synthetic = synthetic_rows()
    csv_data = csv_rows()
    meta = {
        "k": "meta", "freezes": {"utc_now": dt_iso(FROZEN_CLOCK) + " + 1s per reading", "open_year_today": FROZEN_TODAY.isoformat(), "run_id": "sha256('run:<name>')[:32]",
                                 "git_commit": FROZEN_COMMIT, "data_source": "csv", "data_classification": "synthetic", "fixture_account_id": 1001},
        "columns": {t: list(c) for t, c in COLUMNS.items()}, "manifest_columns": list(RUN_MANIFEST_COLUMNS),
        "section_9_query_count": section_9_query_count(), "assumptions": rcc._assumption_identity(), "input_columns": list(INPUT_COLUMNS),
        "designations": {"legacy": [[k, v] for k, v in _DESIGNATION_HISTORY.items()], "source": [[c, u, v] for (c, u), v in _SOURCE_DESIGNATIONS.items()], "synthetic_ga_default": _SYNTHETIC_GA_DEFAULT},
        **oracle.stamp(),
    }
    lines = [dumps(meta)]
    lines += ph.helper_lines(csv_data, synthetic)
    for name, args, overrides, source in runs(synthetic):
        if source == "csv":
            pps.load_pay_periods = real_loader  # the real CSV loader, not a previous subject's source
            record = execute(name, args, overrides)
            record["source"] = {"kind": "csv", "rows": len(csv_data)}
        else:
            serve({source: synthetic[source]})
            record = execute(name, args, overrides)
            record["source"] = {"kind": "synthetic", "client": source, "rows": len(synthetic[source])}
        lines.append(dumps(record))
        print(name, record.get("err") or {t: v["n"] for t, v in record["out"]["tables"].items()}, file=sys.stderr)
    main = gzip_text(lines)
    inputs = gzip_text([dumps({"k": "meta", "input_columns": list(INPUT_COLUMNS), **oracle.stamp()})]
                       + [dumps({"k": "rows", "client": c, "columns": list(INPUT_COLUMNS), "digest": hashlib.sha256(dumps(trimmed(r)).encode()).hexdigest(), "rows": trimmed(r)}) for c, r in sorted(synthetic.items())])
    return main, inputs


def dt_iso(d: datetime) -> str:
    return d.isoformat()


def gzip_text(lines: list) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(("\n".join(lines) + "\n").encode("ascii"))
    return buf.getvalue()


def main() -> int:
    import logging, warnings

    logging.disable(logging.CRITICAL)  # the mediator logs every failed command; the record already carries the exception
    warnings.simplefilter("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data, inputs = build()
    files = {args.out / "gold_payload.jsonl.gz": data, args.out / "gold_payload_input.jsonl.gz": inputs}
    if args.check:
        stale = [p.name for p, b in files.items() if not p.exists() or p.read_bytes() != b]
        print("gold_payload goldens are current" if not stale else "STALE " + ", ".join(stale), file=sys.stderr)
        return 1 if stale else 0
    for path, blob in files.items():
        path.write_bytes(blob)
        print(f"wrote {path} ({len(blob)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
