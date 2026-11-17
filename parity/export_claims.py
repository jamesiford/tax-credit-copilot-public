"""Golden vectors for ``domain/claims.py`` (stage DS4, claims family).

Calls the production module over: every claim the Python tests build, status x provenance x base-year x money grids with
both sides of the 1.00 materiality threshold, headcount grids on both sides of the on-the-line edge, construction errors,
every legal and illegal lifecycle transition, ``declining_reading`` series, ``ProgramEngagement``, the private ``_money``
coercion, the enum tables, raw ``decimal`` operations (the port re-implements the 28-digit context) and a seeded random batch.

Line format (JSONL, gzip, mtime 0): ``{"k":"call","id":n,"fn":name,"out":tree,"args":{...}}`` or
``{"k":"call",...,"err":"TypeName","msg":str(exception)}``. See ``claims_cases.enc`` for the tagged values.
Calls that need ``uuid4()`` / ``now()`` have them replaced by a deterministic counter and a fixed instant, recorded as
``new_claim_id`` / ``now`` in the arguments, because those are the only non-reproducible inputs.

Usage: python parity/export_claims.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
from domain import claims as cl  # noqa: E402
from domain.claims import ClaimStatus as S, ProgramClaim, ProgramEngagement, Provenance as P  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "claims.jsonl.gz"
SEED = 20261115


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


def claim_out(c: ProgramClaim) -> dict:
    props = {
        "cell_key": list(c.cell_key), "is_current": c.is_current, "status_is_claimed": c.status.is_claimed,
        "verified": c.provenance.verified, "variance_usd": str(c.variance_usd), "variance_is_computable": c.variance_is_computable,
        "outcome": c.outcome.value, "is_exposure": c.is_exposure, "opportunity_usd": str(c.opportunity_usd),
        "net_new_jobs": c.net_new_jobs, "jobs_to_threshold": c.jobs_to_threshold, "jobs_margin": c.jobs_margin,
        "near_threshold": c.near_threshold, "priority_band": c.priority_band.value, "priority_rank": c.priority_band.rank,
    }
    return {"props": props, "wire": c.to_dict()}


def rec_claim(rec: Recorder, kw: dict) -> None:
    rec.call("claim", {"spec": kw}, lambda: claim_out(ProgramClaim(**kw)))


class Patched:
    """Replaces ``uuid4`` and ``_now`` for the duration of one call so that the next id and instant are recorded inputs."""

    def __init__(self, new_id: str, now: datetime) -> None:
        self.new_id, self.now = new_id, now

    def __enter__(self):
        self._uuid, self._now = cl.uuid.uuid4, cl._now
        cl.uuid.uuid4 = lambda: uuid.UUID(self.new_id)
        cl._now = lambda: self.now

    def __exit__(self, *exc):
        cl.uuid.uuid4, cl._now = self._uuid, self._now


def rec_transition(rec: Recorder, n: int, base: dict, kw: dict) -> None:
    new_id = str(uuid.UUID(int=n))
    now = datetime(2027, 5, 6, 7, 8, 9, 123456, tzinfo=timezone.utc)

    def run():
        c = ProgramClaim(**base)
        with Patched(new_id, now):
            return c.transition_to(**kw).to_dict()

    rec.call("transition", {"spec": base, "transition": kw, "new_claim_id": new_id, "now": now}, run)


def rec_declining(rec: Recorder, specs: list[dict]) -> None:
    rec.call("declining_reading", {"claims": specs}, lambda: cl.declining_reading([ProgramClaim(**s) for s in specs]))


def rec_money(rec: Recorder, value) -> None:
    rec.call("_money", {"value": value}, lambda: str(cl._money(value)))


def rec_engagement(rec: Recorder, kw: dict) -> None:
    rec.call("engagement", {"spec": kw}, lambda: ProgramEngagement(**kw).to_dict())


def enums_out() -> dict:
    return {
        "status": {s.value: {"is_claimed": s.is_claimed, "allowed": sorted(t.value for t in cl._ALLOWED_TRANSITIONS[s])} for s in S},
        "provenance": {p.value: p.verified for p in P},
        "band": {b.value: b.rank for b in cl.PriorityBand},
        "outcome": [o.value for o in cl.Outcome],
        "scope": [e.value for e in cl.EngagementScope],
        "materiality_usd": str(cl.MATERIALITY_USD),
        "on_the_line_jobs": cl.ON_THE_LINE_JOBS,
    }


def dec_ops(rec: Recorder, rng: random.Random) -> None:
    """Raw ``decimal`` arithmetic under the default 28-digit context: the semantics ``PyDecimalOps`` must reproduce."""
    pool = [Decimal(x) for x in ("0", "-0", "0.00", "-0.00", "1", "-1", "1.00", "1.01", "0.99", "140000.00", "-140000.99", "1E+22", "1E-7", "5E-324",
                                 "9" * 28, "9" * 29, "1" * 35, "-" + "9" * 30, "1E+30", "1E-30", "123456789012345678901234567.5", "2.50", "-3.5E+3",
                                 "0E+5", "-0E-5", "0.5", "4.5", "1E+40", "0E-100", "12345678.91")]
    pairs = [(a, b) for a in pool for b in pool]
    pairs += [(cc.rand_decimal(rng), cc.rand_decimal(rng)) for _ in range(3500)]
    for a, b in pairs:
        rec.call("dec_add", {"a": a, "b": b}, lambda: str(a + b))
        rec.call("dec_sub", {"a": a, "b": b}, lambda: str(a - b))
        rec.call("dec_cmp", {"a": a, "b": b}, lambda: {"lt": a < b, "le": a <= b, "eq": a == b, "gt": a > b, "ge": a >= b})
        rec.call("dec_max0", {"a": a}, lambda: str(max(Decimal("0"), a)))
    for a in pool + [cc.rand_decimal(rng) for _ in range(1200)]:
        rec.call("dec_neg", {"a": a}, lambda: str(-a))
        rec.call("dec_abs", {"a": a}, lambda: str(abs(a)))
    for _ in range(1500):
        xs = [cc.rand_decimal(rng) if rng.random() < 0.8 else rng.choice(pool) for _ in range(rng.randint(0, 8))]
        rec.call("dec_sum", {"xs": xs}, lambda: str(sum(xs, Decimal("0"))))
        rec.call("dec_sum_neg", {"xs": xs}, lambda: str(sum((-x for x in xs), Decimal("0"))))


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    cc.reset()
    rec = Recorder()
    rec.call("enums", {}, enums_out)
    for kw in cc.test_specs(S, P):
        rec_claim(rec, kw)
    for kw in cc.money_set(S, P) + cc.headcount_set(S, P) + cc.error_specs(S, P):
        rec_claim(rec, kw)
    for _ in range(3000):
        rec_claim(rec, cc.rand_spec(rng, S, P))
    for n, (base, kw) in enumerate(cc.transition_cases(S, P), start=1):
        rec_transition(rec, n, base, kw)
    for series in cc.declining_series(S):
        rec_declining(rec, series)
    for _ in range(1200):
        k = rng.randint(0, 6)
        years = rng.sample(range(2018, 2027), k) if rng.random() < 0.7 else [rng.randint(2020, 2024) for _ in range(k)]
        specs = []
        for y in years:
            s = cc.rand_spec(rng, S, P, years=(y,))
            s["average_headcount"] = rng.choice([None, round(rng.uniform(20, 120), 2), 60.0, 60.0])
            s["identified_usd"] = rng.choice([0, "0", Decimal("1.00"), Decimal("500"), Decimal("1E+3"), rng.randint(0, 10 ** 6)])
            specs.append(s)
        rec_declining(rec, specs)
    for v in cc.MONEY_POOL + [cc.rand_money(rng) for _ in range(800)] + ["abc", "", "1,000", True, False, [1]]:
        rec_money(rec, v)
    for code in ("ga_jtc", "GA_JTC", "Straße", "x"):
        for sc in list(cl.EngagementScope) + [None]:
            kw = {"client_id": 1001, "program_code": code, "effective_from": cc.FIXED}
            if sc is not None:
                kw["scope"] = sc
            rec_engagement(rec, kw)
            rec_engagement(rec, {**kw, "effective_to": cc.FIXED + timedelta(days=9, microseconds=5), "note": "n", "set_by": "who", "set_at": cc.FIXED})
    dec_ops(rec, rng)
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
        print("claims golden is current" if ok else "STALE claims golden", file=sys.stderr)
        return 0 if ok else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
