"""Shared scenario builders for ``export_claims.py`` and ``export_coverage.py`` (stage DS4, claims family).

A *spec* is the keyword dictionary handed to ``ProgramClaim(**spec)``. ``enc`` turns Python values into the JSON the C#
replay reads: a ``Decimal`` is ``{"$dec": "<str>"}``, a ``datetime`` is ``{"$dt": iso}``, a ``date`` is ``{"$date": iso}``,
enums are their string values, floats keep their ``repr`` (non-finite as ``NaN``/``Infinity``), ints stay ints.

``claim_id`` and ``effective_from`` are always given explicitly: their defaults are ``uuid4()`` and ``now()``, which are not
reproducible, so the C# tests check those two defaults by shape instead of by golden.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
INF = float("inf")
NAN = float("nan")
_COUNTER = [0]


def reset() -> None:
    _COUNTER[0] = 0


def next_id() -> str:
    _COUNTER[0] += 1
    return f"cl-{_COUNTER[0]:06d}"


def enc(x):
    """JSON-able view of a spec, an argument tree or an output tree."""
    if isinstance(x, datetime):
        return {"$dt": x.isoformat()}
    if isinstance(x, date):
        return {"$date": x.isoformat()}
    if isinstance(x, Decimal):
        return {"$dec": str(x)}
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, dict):
        return {k: enc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [enc(v) for v in x]
    return x


def spec(**kw) -> dict:
    """Keyword set for one claim, with a fresh ``claim_id`` and a fixed ``effective_from`` unless given."""
    base = {"client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "claim_id": next_id(), "effective_from": FIXED}
    base.update(kw)
    return base


def dec(sign: int, digits: str, exp: int) -> Decimal:
    return Decimal((sign, tuple(int(c) for c in digits), exp))


# ------------------------------------------------------------------------------------------ the python tests' inputs

def test_specs(S, P):
    """Every ``ProgramClaim(...)`` the Python tests build (claims_domain, base_year_variance, priority_bands, coverage_totals)."""
    D = Decimal
    a = dict(status=S.ASSESSED, decided_by="analyst@example.com")
    ax = lambda **k: spec(**{**a, **k})  # noqa: E731
    out = [
        ax(identified_usd=0, claimed_usd=0),
        ax(identified_usd=D("140000"), claimed_usd=0),
        ax(status=S.CLAIMED, identified_usd=D("140000.00"), claimed_usd=D("140000.00")),
        ax(status=S.CLAIMED, identified_usd=D("480000"), claimed_usd=D("140000")),
        ax(status=S.CLAIMED, identified_usd=D("100000"), claimed_usd=D("140000")),
        ax(status=S.CLAIMED, identified_usd=D("140000"), claimed_usd=D("100000")),
        ax(status=S.CLAIMED, identified_usd=D("140000.00"), claimed_usd=D("140000.99")),
        ax(status=S.CLAIMED, identified_usd=D("140000.00"), claimed_usd=D("140001.01")),
        ax(status=S.CERTIFIED, identified_usd=D("140000"), claimed_usd=D("140000"), certified_usd=D("95000")),
        ax(status=S.NOT_ASSESSED, identified_usd=0),
        ax(status=S.DECLINED),
        ax(status=S.DECLINED, decline_reason="Client takes the R&D credit instead."),
        ax(status=S.DECLINED, decline_reason="   "),
        spec(client_id=1001, program_code="GA_JTC", tax_year=None),
        ax(status=S.CERTIFIED),
        ax(status=S.DECLINED, decline_reason="Not this year."),
        ax(identified_usd=D("140000")),
        ax(provenance=P.CLIENT_ASSERTED, status=S.CLAIMED, claimed_usd=D("90000")),
        ax(identified_usd=D("140000.55")),
        ax(identified_usd=0.1, claimed_usd="0.2"),
        ax(identified_usd=0, average_headcount=74.1, base_average_headcount=73.0, threshold_jobs=2.0),
        ax(identified_usd=0, average_headcount=73.0, base_average_headcount=73.0, threshold_jobs=50.0),
        ax(average_headcount=84.0, base_average_headcount=73.0, threshold_jobs=2.0),
        ax(average_headcount=60.0, base_average_headcount=73.0, threshold_jobs=2.0),
        ax(),
        ax(average_headcount=74.0, base_average_headcount=73.0),
    ]
    for p in P:
        out.append(ax(provenance=p))
    # base-year family
    by = dict(client_id=4242, status=S.CLAIMED, provenance=P.CLIENT_ASSERTED, identified_usd=D("0"), claimed_usd=D("410000"),
              average_headcount=226.76, base_average_headcount=226.76, threshold_jobs=2.0, is_base_year=True)
    out += [
        spec(**by),
        spec(**{**by, "claimed_usd": D("0")}),
        spec(**{**by, "identified_usd": D("500000"), "claimed_usd": D("1")}),
        spec(**{**by, "tax_year": 2022, "identified_usd": D("31185"), "claimed_usd": D("95000"), "average_headcount": 117.08,
                "base_average_headcount": 106.17, "is_base_year": False}),
        spec(**{**by, "tax_year": 2024, "identified_usd": D("45535"), "claimed_usd": D("45535"), "is_base_year": False}),
        spec(**{**by, "tax_year": 2024, "identified_usd": D("0"), "claimed_usd": D("95000"), "average_headcount": 60.0,
                "base_average_headcount": 60.0, "is_base_year": False}),
    ]
    # priority bands
    pb = dict(client_id=2001, status=S.ASSESSED)
    mk = lambda **k: spec(**{**pb, **k})  # noqa: E731
    out += [
        mk(identified_usd=D("0"), average_headcount=11.4, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(identified_usd=D("607110"), average_headcount=90.0, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(average_headcount=11.5, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(average_headcount=60.0, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(status=S.CLAIMED, identified_usd=D("1000"), claimed_usd=D("90000"), average_headcount=11.5, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(is_base_year=True, identified_usd=D("0")),
        mk(status=S.NOT_ASSESSED),
        mk(identified_usd=D("50000"), average_headcount=None),
        mk(status=S.CLAIMED, identified_usd=D("50000"), claimed_usd=D("50000"), average_headcount=12.5, base_average_headcount=10.0, threshold_jobs=2.0),
        mk(identified_usd=D("140000"), average_headcount=84.0, base_average_headcount=73.0, threshold_jobs=2.0),
    ]
    for margin in (-1.0, 0.0, 1.0):
        out.append(mk(average_headcount=10.0 + 2.0 + margin, base_average_headcount=10.0, threshold_jobs=2.0))
    # coverage totals
    out.append(spec(claim_id="GA_JTC-2023-opp", entity_id=None, status=S.ASSESSED, identified_usd=D("40000"), claimed_usd=D("0")))
    out.append(spec(claim_id="GA_JTC-2023-exp", entity_id=None, status=S.CLAIMED, identified_usd=D("0"), claimed_usd=D("40000")))
    return out


def declining_year(S, tax_year, headcount, identified="0", **kw):
    base = {"base_average_headcount": 40.0, "threshold_jobs": 2.0}
    return spec(**{"client_id": 2001, "claim_id": f"c{tax_year}", "tax_year": tax_year, "status": S.ASSESSED, "average_headcount": headcount,
                   "identified_usd": Decimal(identified), **base, **kw})


def declining_series(S) -> list[list[dict]]:
    """The six series ``test_priority_bands.py`` feeds ``declining_reading`` plus variants around each rule."""
    y = lambda *a, **k: declining_year(S, *a, **k)  # noqa: E731
    series = [
        [y(2021, 85.75, "163345"), y(2022, 100.75, "45500"), y(2023, 92.84), y(2024, 70.34), y(2025, 61.42, base_average_headcount=70.34)],
        [y(2021, 58.82, "20000"), y(2022, 50.92), y(2023, 55.10), y(2024, 59.25), y(2025, 71.42)],
        [y(2023, 30.0), y(2024, 25.0), y(2025, 20.0)],
        [y(2025, 20.0, "5000")],
        [y(2024, 50.0, "9000"), y(2025, 50.0)],
        [y(2020, 200.0, is_base_year=True), y(2024, 60.0, "9000"), y(2025, 50.0)],
        [],
        [y(2024, 50.0, "9000"), y(2025, 49.99)],
        [y(2024, 50.0, "0.5"), y(2025, 49.0)],            # earned only 50 cents
        [y(2024, 50.0, "1.00"), y(2025, 49.0)],
        [y(2025, 49.0), y(2024, 50.0, "9000")],            # input order is not year order
        [y(2025, 49.0, "9000"), y(2025, 50.0), y(2025, 48.0)],   # duplicate years keep input order (stable sort)
        [y(2022, 10.0, "5"), y(2023, 70.0, "5"), y(2024, 70.0, "5"), y(2025, 60.0)],         # tie for peak: first wins
        [y(2022, 70.0, "5"), y(2023, 70.0, "5"), y(2024, 65.0), y(2025, 60.0)],
        [y(2023, 61.0, "5", base_average_headcount=None), y(2024, 60.0, base_average_headcount=None)],
        [y(2023, 61.0, "5"), y(2024, 60.0, base_average_headcount=60.0)],                      # latest == base: not below
        [y(2023, 61.0, "5"), y(2024, 60.0, base_average_headcount=60.01)],
        [y(2023, 61.0, "5"), y(2024, 60.0, status=S.NOT_ASSESSED, average_headcount=None)],  # unmeasured year is dropped
        [y(2023, NAN, "5"), y(2024, 60.0)],
        [y(2023, 61.0, "5"), y(2024, NAN)],
        [y(2023, 61.0, "5"), y(2024, 60.0), y(2025, NAN)],
        [y(2023, INF, "5"), y(2024, 60.0)],
        [y(2023, 61.0, "5"), y(2024, -INF)],
        [y(2024, 0.1 + 0.2, "5"), y(2025, 0.3)],           # 0.30000000000000004 versus 0.3
        [y(2024, 100.005, "5"), y(2025, 60.001)],          # fallen_by rounds on the binary value
        [y(2024, 100.125, "5"), y(2025, 60.0)],
        [y(2024, 1e308, "5"), y(2025, -1e308)],            # fallen_by overflows to inf
        [y(2022, 90.0, "100000000000000000000000000000"), y(2023, 80.0, "100000000000000000000000000000"), y(2024, 70.0)],   # 30-digit sum rounds
        [y(2022, 90.0, "1E+5"), y(2023, 80.0, "2.50"), y(2024, 70.0)],
        [y(2022, 90.0, "-5"), y(2023, 80.0, "-6"), y(2024, 70.0)],                              # negative identified is not earned
    ]
    # unmeasured / base-year rows mixed in
    series.append([y(2022, 90.0, "7", is_base_year=True), y(2023, 80.0, "7"), y(2024, 70.0)])
    series.append([y(2022, 90.0, "7"), y(2023, 80.0, "7"), y(2024, 70.0, is_base_year=True)])
    return series


# ------------------------------------------------------------------------------------------------ grids and random

MONEY_POOL = [0, 1, 0.5, 0.1, 1.0, 1.01, 140000, 140000.55, -0.0, "0", "1.00", "1.01", "0.99", "-5", " 7 ", "1e3", "1E+2", ".5", "5.",
              "-0", "+7", "007", "0.0100", "1_000", Decimal("0"), Decimal("1.00"), Decimal("1.01"), Decimal("0.99"), Decimal("-0.00"),
              Decimal("140000.00"), Decimal("140000.99"), Decimal("140001.01"), Decimal("1E+22"), Decimal("2.50"),
              Decimal("-3.5"), Decimal("12345678.91"), 10 ** 30, -(10 ** 29), 123456789012345678901234567890,
              Decimal("9" * 28), Decimal("9" * 29), Decimal("1" * 35), 1e22, 1e-7, 5e-324, 1.7976931348623157e308, 123456789.12,
              None]


def rand_decimal(rng: random.Random) -> Decimal:
    ndig = rng.choice([1, 2, 3, 5, 8, 12, 20, 27, 28, 29, 30, 35])
    digits = "".join(rng.choice("0123456789") for _ in range(ndig)) or "0"
    if rng.random() < 0.15:
        digits = "0" * ndig
    return dec(rng.randint(0, 1) if rng.random() < 0.3 else 0, digits, rng.choice([0, 0, -1, -2, -2, -2, -3, -6, 1, 3, -10, -28, 5, -30]))


def rand_money(rng: random.Random):
    r = rng.random()
    if r < 0.45:
        return rand_decimal(rng)
    if r < 0.55:
        return rng.choice(MONEY_POOL)
    if r < 0.7:
        return rng.randint(-10 ** rng.randint(1, 12), 10 ** rng.randint(1, 12))
    if r < 0.85:
        return round(rng.uniform(-1e6, 1e6), rng.choice([0, 1, 2, 3]))
    return rng.choice(["0", "1.00", "12.34", "999999.99", "1e2", " 3.5 ", "-0.00", "2.50"])


def rand_headcount(rng: random.Random, allow_none=True):
    r = rng.random()
    if allow_none and r < 0.12:
        return None
    if r < 0.2:
        return rng.choice([0.0, -0.0, 10.0, 12.0, 2.0, 1.0, -1.0, NAN, INF, -INF, 1e308, 5e-324])
    return round(rng.uniform(0, 300), rng.choice([0, 1, 2, 2, 2, 3, 4]))


def rand_spec(rng: random.Random, S, P, *, client_ids=(1001,), programs=("GA_JTC",), years=(2021, 2022, 2023, 2024)) -> dict:
    status = rng.choice(list(S))
    kw = dict(
        client_id=rng.choice(client_ids), program_code=rng.choice(programs), tax_year=rng.choice(years), status=status,
        provenance=rng.choice(list(P)), identified_usd=rand_money(rng), claimed_usd=rand_money(rng), certified_usd=rand_money(rng),
        average_headcount=rand_headcount(rng), base_average_headcount=rand_headcount(rng), threshold_jobs=rng.choice([None, 2.0, 0.0, 1.0, 50.0, 5.5, -1.0]),
        is_base_year=rng.random() < 0.12, entity_id=rng.choice([None, None, 1, 7]),
    )
    if status is S.DECLINED:
        kw["decline_reason"] = rng.choice(["Not this year.", "x", "R&D instead"])
    if rng.random() < 0.3:
        kw["filed_on"] = date(2020, 1, 1) + timedelta(days=rng.randint(0, 2500))
        kw["filing_reference"] = rng.choice(["IT-CA-2023-0042", "", "ref"])
    if rng.random() < 0.3:
        kw["decided_by"] = rng.choice(["lead@example.com", "", "x"])
        kw["decided_at"] = FIXED + timedelta(microseconds=rng.choice([0, 1, 123456, 999999]), seconds=rng.randint(0, 10 ** 8))
    if rng.random() < 0.2:
        kw["effective_to"] = FIXED + timedelta(days=rng.randint(1, 900))
    for k in ("identified_run_id", "assumption_set_id", "rule_pack_version"):
        if rng.random() < 0.2:
            kw[k] = f"{k}-{rng.randint(1, 99)}"
    return spec(**kw)


def money_set(S, P) -> list[dict]:
    """Status x provenance x base-year x a boundary-rich set of money triples (both sides of the 1.00 materiality)."""
    triples = [(0, 0, 0), ("0.5", 0, 0), ("1.00", 0, 0), ("1.01", 0, 0), (140000, 0, 0), (0, 140000, 0), (140000, 140000, 140000),
               ("140000.00", "140000.99", "0"), ("140000.00", "140001.01", "0"), ("140000.00", "140001.00", "0"), ("140000.00", "139999.00", "0"),
               ("140000.00", "139998.99", "0"), (100000, 140000, 95000), (140000, 100000, 0), ("100", "100", "98.99"), ("100", "100", "99.00"),
               ("100", "100", "98.50"), (Decimal("1E+22"), Decimal("1E+22"), Decimal("9E+21")), (Decimal("-5"), 0, 0), (0, Decimal("-5"), 0),
               (Decimal("-0.00"), Decimal("-0"), 0), (Decimal("9" * 30), 1, 0), (Decimal("1" * 30), Decimal("1" * 30), Decimal("2" * 30))]
    out = []
    for status in S:
        for prov in P:
            for base in (False, True):
                for ident, claimed, cert in triples:
                    kw = dict(status=status, provenance=prov, is_base_year=base, identified_usd=ident, claimed_usd=claimed, certified_usd=cert)
                    if status is S.DECLINED:
                        kw["decline_reason"] = "because"
                    out.append(spec(**kw))
    return out


def headcount_set(S, P) -> list[dict]:
    """Headcount x base x threshold around both sides of the on-the-line edge, across every provenance and money regime."""
    out = []
    margins = [-1.01, -1.006, -1.005, -1.004, -1.0, -0.5, -0.004, -0.001, 0.0, 0.001, 0.004, 0.5, 1.0, 1.004, 1.005, 1.006, 1.01, 48.0]
    for m in margins:
        for avg in (10.0 + 2.0 + m, 73.0 + 2.0 + m):
            base = 10.0 if avg < 50 else 73.0
            out.append(spec(status=S.ASSESSED, identified_usd=0, average_headcount=avg, base_average_headcount=base, threshold_jobs=2.0))
    for avg in (13.0, 11.0):
        for edge in (math.nextafter(avg, 0.0), avg, math.nextafter(avg, 100.0)):
            out.append(spec(status=S.ASSESSED, average_headcount=edge, base_average_headcount=10.0, threshold_jobs=2.0))
    for avg in (None, 74.1, 11.4, 12.5, 60.0, 0.0, -1.0, NAN, INF, -INF, 1e308, 5e-324):
        for base in (None, 10.0, 73.0, 0.0, NAN, INF, 1e308):
            for thr in (None, 2.0, 0.0, 50.0, -1.0, 1e308):
                out.append(spec(status=S.ASSESSED, identified_usd=0, average_headcount=avg, base_average_headcount=base, threshold_jobs=thr))
    for prov in P:
        for status in (S.ASSESSED, S.CLAIMED, S.CERTIFIED, S.NOT_ASSESSED, S.PROPOSED):
            for ident, claimed, cert in [(0, 0, 0), ("1000", "90000", "0"), ("90000", "1000", "0"), ("31185", "95000", "0"), ("50000", "50000", "40000"),
                                         ("1.00", 0, 0), ("1.01", 0, 0), (0, 0, 0)]:
                for ah, bh, th in [(11.5, 10.0, 2.0), (12.5, 10.0, 2.0), (60.0, 10.0, 2.0), (None, None, None), (13.0, 10.0, 2.0), (14.0, 10.0, 2.0)]:
                    out.append(spec(status=status, provenance=prov, identified_usd=ident, claimed_usd=claimed, certified_usd=cert,
                                    average_headcount=ah, base_average_headcount=bh, threshold_jobs=th))
    return out


def error_specs(S, P) -> list[dict]:
    out = []
    for code in (None, "", " ", "\t", "ga_jtc", "Straße", "ǆ", "ŉ", "ﬁ", "ı", "i̇", "\U00010428", "ΐ", "Éa", "a\u00a0", "\u2003x"):
        out.append(spec(program_code=code, status=S.ASSESSED))
        out.append(spec(program_code=code, status=S.DECLINED))
        out.append(spec(program_code=code, status=S.DECLINED, decline_reason="r"))
    for ty in (None, 0, -1, 1, 2023, 10 ** 12):
        out.append(spec(tax_year=ty, status=S.ASSESSED))
    for money in ("abc", "", " ", "1,000", "--1", "1e", "0x10", "1 000", "1.2.3", "e5", "+", "-", "_1", "1_", "1__0", "True", True, False, [1], "1e+", ".", "1.e2"):
        for field in ("identified_usd", "claimed_usd", "certified_usd"):
            out.append(spec(status=S.ASSESSED, **{field: money}))
    for reason in (None, "", "  ", "\t\n", "\u00a0", "\u2003", "\u200b", "x", " x ", "\u0085", "\x1f", "\x1c"):
        out.append(spec(status=S.DECLINED, decline_reason=reason))
    # both a bad code and a bad year: the code is checked first; a bad year and a bad money: the year first
    out.append(spec(program_code="", tax_year=None))
    out.append(spec(tax_year=None, identified_usd="abc"))
    out.append(spec(identified_usd="abc", status=S.DECLINED))
    return out


def transition_cases(S, P) -> list[tuple[dict, dict]]:
    """(base spec, transition kwargs). Every status pair, then every option."""
    D = Decimal
    out = []
    for src in S:
        base = dict(status=src, identified_usd=D("140000"), claimed_usd=D("100"), certified_usd=D("90"))
        if src is S.DECLINED:
            base["decline_reason"] = "Not this year."
        for dst in S:
            out.append((spec(**base), {"status": dst, "decided_by": "lead@example.com"}))
            out.append((spec(**base), {"status": dst, "decided_by": "lead@example.com", "decline_reason": "r2"}))
            out.append((spec(**base), {"status": dst, "decided_by": "lead@example.com", "decline_reason": ""}))
            out.append((spec(**base), {"status": dst, "decided_by": "lead@example.com", "decline_reason": "   "}))
    live = dict(status=S.PROPOSED, identified_usd=D("140000"), provenance=P.COMPUTED, filed_on=date(2023, 1, 1), filing_reference="old",
                decided_by="first", decided_at=FIXED, decline_reason=None)
    full = {"decided_by": "filer@example.com", "claimed_usd": D("140000"), "certified_usd": D("140000"), "filed_on": date(2024, 3, 15),
            "filing_reference": "IT-CA-2023-0042", "provenance": P.FILED_BY_US, "at": FIXED + timedelta(days=30, microseconds=7)}
    out.append((spec(**live), {"status": S.CLAIMED, **full}))
    for by in ("", "  ", None, "\u00a0", "x", " y ", "\u200b"):
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": by}))
    for money in (None, 0, 1, 1.5, 0.1, "2.50", " 3 ", D("1E+3"), D("-0"), 10 ** 30, "abc", True, "1e2", 1e22, D("9" * 30)):
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "claimed_usd": money}))
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "certified_usd": money}))
    for prov in P:
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "provenance": prov}))
    for filed in (None, date(2024, 2, 29), date(1, 1, 1)):
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "filed_on": filed}))
    for ref in (None, "", "R-1"):
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "filing_reference": ref}))
    for at in (None, FIXED, datetime(2030, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc), datetime(2024, 6, 1, 12, 0, 0),
               datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5, minutes=-30)))):
        out.append((spec(**live), {"status": S.CLAIMED, "decided_by": "d", "at": at}))
    # the python tests' happy path, step by step
    p1 = dict(status=S.ASSESSED, decided_by="analyst@example.com", identified_usd=D("140000"))
    out.append((spec(**p1), {"status": S.PROPOSED, "decided_by": "lead@example.com"}))
    out.append((spec(**{**p1, "status": S.PROPOSED}), {"status": S.CLAIMED, "decided_by": "filer@example.com", "claimed_usd": D("140000"),
                                                      "filed_on": date(2024, 3, 15), "filing_reference": "IT-CA-2023-0042", "provenance": P.FILED_BY_US}))
    out.append((spec(**{**p1, "status": S.CLAIMED, "claimed_usd": D("140000"), "provenance": P.FILED_BY_US}),
                {"status": S.CERTIFIED, "decided_by": "filer@example.com", "certified_usd": D("140000"), "provenance": P.AUTHORITY_CONFIRMED}))
    out.append((spec(**{**p1, "status": S.DECLINED, "decline_reason": "Not this year."}), {"status": S.PROPOSED, "decided_by": "lead@example.com"}))
    out.append((spec(**p1), {"status": S.CERTIFIED, "decided_by": "lead@example.com"}))
    out.append((spec(**p1), {"status": S.CLAIMED, "decided_by": "lead@example.com"}))
    out.append((spec(**{**p1, "status": S.CERTIFIED}), {"status": S.ASSESSED, "decided_by": "lead@example.com"}))
    out.append((spec(**p1), {"status": S.PROPOSED, "decided_by": ""}))
    return out
