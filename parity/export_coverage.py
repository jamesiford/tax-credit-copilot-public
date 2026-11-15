"""Golden vectors for ``domain/coverage.py`` (stage DS4, claims family).

``totals``, ``totals_by_program``, ``matrix``, ``group_by_client`` and ``situation`` are called over claim lists built from
the Python tests' inputs, every reachable outcome / priority band / provenance combination, tie-heavy rankings (equal band,
equal identified, equal float image of different decimals, same year), unsorted programmes and clients, 28+ digit sums,
engagement maps (missing, ``None``, every scope, case-mismatched codes) and a seeded random batch.

Line format as in ``export_claims.py``. ``group_by_client`` is recorded as ``[[client_id, [claim_id, ...]], ...]`` in
insertion order (the claims are identified by their unique ``claim_id``).

Usage: python parity/export_coverage.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import claims_cases as cc  # noqa: E402
from domain import coverage as cov  # noqa: E402
from domain.claims import ClaimStatus as S, EngagementScope as E, ProgramClaim, Provenance as P  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "coverage.jsonl.gz"
SEED = 20261116


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


class Recorder:
    def __init__(self) -> None:
        self.lines: list = []
        self.counts: dict[str, int] = {}
        self.errors = 0

    def call(self, fn: str, args: dict, run) -> None:
        text_in = dumps(cc.enc(args))
        try:
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "out": cc.enc(run())}
        except Exception as e:  # the exception type and message are part of the contract
            self.errors += 1
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "err": type(e).__name__, "msg": str(e)}
        self.counts[fn] = self.counts.get(fn, 0) + 1
        self.lines.append((text_in, rec))


def record_list(rec: Recorder, specs: list[dict], rng: random.Random) -> None:
    kept = []
    for s in specs:
        try:
            ProgramClaim(**s)
        except Exception:  # construction errors are covered by the claims golden; a list holds only valid cells
            continue
        kept.append(s)
    specs = kept
    claims = [ProgramClaim(**s) for s in specs]
    args = {"claims": specs}
    rec.call("totals", args, lambda: cov.totals(claims))
    rec.call("totals_by_program", args, lambda: cov.totals_by_program(claims))
    rec.call("group_by_client", args, lambda: [[k, [c.claim_id for c in v]] for k, v in cov.group_by_client(claims).items()])
    rec.call("situation", args, lambda: cov.situation(claims))
    codes = sorted({c.program_code for c in claims}) + ["ga_jtc", "NOPE"]
    engagements = {}
    for code in codes:
        r = rng.random()
        if r < 0.25:
            continue
        engagements[code] = None if r < 0.35 else rng.choice(list(E))
    rec.call("matrix", {"claims": specs, "engagements": engagements}, lambda: cov.matrix(claims, engagements))
    all_out = {code: E.OUT_OF_SCOPE for code in codes}
    rec.call("matrix", {"claims": specs, "engagements": all_out}, lambda: cov.matrix(claims, all_out))


def targeted_lists() -> list[list[dict]]:
    D = Decimal
    out: list[list[dict]] = [[]]
    tests = cc.test_specs(S, P)
    out += [[t] for t in tests]
    out.append(tests)
    out.append(tests[:10])
    opp = lambda code, y, ident: cc.spec(claim_id=f"{code}-{y}-opp", entity_id=None, program_code=code, tax_year=y, status=S.ASSESSED,  # noqa: E731
                                         identified_usd=D(ident), claimed_usd=D("0"))
    exp = lambda code, y, claimed: cc.spec(claim_id=f"{code}-{y}-exp", entity_id=None, program_code=code, tax_year=y, status=S.CLAIMED,  # noqa: E731
                                           identified_usd=D("0"), claimed_usd=D(claimed))
    out.append([opp("GA_JTC", 2022, "40000"), exp("GA_JTC", 2023, "40000")])
    out.append([opp("GA_JTC", 2022, "40000"), opp("GA_JTC", 2023, "60000"), opp("SC_JTC", 2023, "10000")])
    out.append([opp("GA_JTC", 2022, "40000.33"), opp("GA_JTC", 2023, "60000.33"), opp("SC_JTC", 2023, "10000.34")])
    out.append([opp("GA_JTC", 2023, "12345678.91")])
    # ties: same band + same identified -> by tax_year; float image equal for different decimals -> by tax_year
    out.append([opp("A", 2025, "100"), opp("A", 2023, "100"), opp("A", 2024, "100"), opp("A", 2023, "100.00")])
    out.append([opp("A", 2025, "10000000000000000.01"), opp("A", 2024, "10000000000000000.02"), opp("A", 2026, "10000000000000000.00")])
    out.append([opp("A", 2025, "0.1"), opp("A", 2024, "0.10000000000000001"), opp("A", 2023, "0.1000000000000000055511151231257827")])
    out.append([opp("A", 2023, "1E+400"), opp("A", 2022, "1E+500"), opp("A", 2021, "5")])
    out.append([cc.spec(identified_usd=D("-0"), status=S.ASSESSED), cc.spec(identified_usd=D("0.00"), status=S.ASSESSED), cc.spec(identified_usd=D("-0.00"), status=S.ASSESSED)])
    out.append([opp("A", 2023, "9" * 30), opp("A", 2022, "1"), opp("B", 2022, "1" * 29)])
    # unsorted programmes (code point order) and clients
    out.append([opp(c, 2023, "5") for c in ("ZZ", "aa", "GA_JTC", "SC_JTC", "É", "Ǆ", "ß", "X1", "x1", "\U00010428")])
    out.append([cc.spec(client_id=cid, program_code="GA_JTC", status=S.ASSESSED, identified_usd=D("5")) for cid in (3, -1, 2, 3, 0, 2, 10 ** 12, 1)])
    # every outcome x band x provenance reachable cell, in one list and singly
    cells = [t for t in cc.money_set(S, P)][::37]
    out.append(cells)
    out += [[c] for c in cells[:40]]
    # one cell of each priority band in scrambled order, with bands' ties on identified
    bands = [
        cc.spec(claim_id="exposed", status=S.CLAIMED, identified_usd=D("1000"), claimed_usd=D("90000"), average_headcount=30.0, base_average_headcount=10.0, threshold_jobs=2.0),
        cc.spec(claim_id="line", status=S.ASSESSED, identified_usd=D("0"), average_headcount=11.4, base_average_headcount=10.0, threshold_jobs=2.0),
        cc.spec(claim_id="line2", status=S.ASSESSED, identified_usd=D("500"), average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0),
        cc.spec(claim_id="big", status=S.ASSESSED, identified_usd=D("607110"), average_headcount=90.0, base_average_headcount=10.0, threshold_jobs=2.0),
        cc.spec(claim_id="notassessed", status=S.NOT_ASSESSED),
        cc.spec(claim_id="settled", status=S.ASSESSED, identified_usd=D("0")),
        cc.spec(claim_id="base", status=S.ASSESSED, is_base_year=True, tax_year=2020),
        cc.spec(claim_id="asserted", status=S.CLAIMED, provenance=P.CLIENT_ASSERTED, identified_usd=D("31000"), claimed_usd=D("95000")),
    ]
    out.append(bands)
    out.append(bands[::-1])
    out.append(bands[3:] + bands[:3])
    return out


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    cc.reset()
    rec = Recorder()
    for specs in targeted_lists():
        record_list(rec, specs, rng)
    for _ in range(1500):
        n = rng.choice([0, 1, 1, 2, 3, 4, 5, 6, 8, 12])
        programs = rng.choice([("GA_JTC",), ("GA_JTC", "SC_JTC"), ("GA_JTC", "SC_JTC", "FED_WOTC", "ga_jtc", "Straße")])
        clients = rng.choice([(1001,), (1001, 2001), (1001, 2001, 2002, 7)])
        specs = [cc.rand_spec(rng, S, P, client_ids=clients, programs=programs, years=(2020, 2021, 2022, 2023, 2024, 2025)) for _ in range(n)]
        if rng.random() < 0.3:   # force identified ties so the secondary keys decide
            v = rng.choice([Decimal("100"), Decimal("0"), Decimal("1E+2"), 100])
            for s in specs:
                s["identified_usd"] = v
        record_list(rec, specs, rng)
    meta = {"k": "meta", "seed": seed, "calls": len(rec.lines), "errors": rec.errors, "counts": rec.counts, **oracle.stamp()}
    lines = [dumps(meta)]
    for text_in, rec_line in rec.lines:
        body = dumps(rec_line)
        lines.append(body[:-1] + ',"args":' + text_in + "}")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(("\n".join(lines) + "\n").encode("ascii"))
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = build(args.seed)
    if args.check:
        ok = args.out.exists() and args.out.read_bytes() == data
        print("coverage golden is current" if ok else "STALE coverage golden", file=sys.stderr)
        return 0 if ok else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
