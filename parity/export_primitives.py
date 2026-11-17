"""Export numeric/text/date primitive test vectors from CPython (the oracle).

Why: the C# port must reproduce Python's float/Decimal/date/string behaviour
bit for bit. C# cannot reproduce Python's random stream, so the *exported file
is the fixture*. Every double is stored three ways (repr, float.hex, IEEE-754
bits) so a bit pattern is never ambiguous.

Output: parity/goldens/primitives.jsonl.gz  (one JSON object per line)
Deterministic: seeded; running twice yields identical bytes (gzip mtime fixed).

Usage:  python parity/export_primitives.py [--out PATH] [--seed N] [--check]
Only new files under parity/ are written; no existing Python is touched.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import decimal
import gzip
import io
import json
import math
import random
import struct
import sys
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

SEED = 20261114
DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "primitives.jsonl.gz"


def bits(x: float) -> int:
    return struct.unpack("<q", struct.pack("<d", x))[0]


def from_bits(b: int) -> float:
    return struct.unpack("<d", struct.pack("<q", b))[0]


def D(x: float) -> dict:
    """A double in all three unambiguous encodings."""
    return {"r": repr(x), "h": x.hex() if math.isfinite(x) else repr(x), "b": bits(x)}


def adversarial_doubles(rng: random.Random) -> list[float]:
    base = [
        0.0, -0.0, 0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 0.125, 0.375, 0.625, 0.875, -0.125,
        2.675, 1.005, 1.015, 1.025, 0.285, 1.115, 4.35, 8.345, 0.045, 0.055, 1.45, 2.345,
        1e15 + 0.5, 4503599627370496.5, 9007199254740993.0, 1e22, 1e23, 1e300, -1e300,
        1.7976931348623157e308, 5e-324, 2.2250738585072014e-308, 2.225073858507201e-308,
        1e-7, 1e-5, 0.0001, 0.00001, 1e16, 1e17, 123456789012345680.0, 0.1 + 0.2, 1 / 3,
        2 / 3, 100.0, 99.995, 99.985, 1234.5678, 35.0, 34.995, 34.9949999, 636.0, 635.995,
        12345678.125, 0.015, 0.025, 0.035, 0.045, 0.055, 0.065, 0.075, 0.085, 0.095,
    ]
    out = list(base)
    for k in range(-6, 7):  # decimal-looking ties at every scale
        for m in range(1, 40):
            out.append(m * 10.0 ** k + 5 * 10.0 ** (k - 1))
            out.append(float(f"{m}.{m:03d}5"))
    for _ in range(3000):  # exact binary ties n + 1/2^k
        out.append(rng.randint(-5000, 5000) / (1 << rng.randint(1, 12)))
    for _ in range(3000):  # neighbours of ties
        t = rng.randint(-100000, 100000) / (10 ** rng.randint(1, 6)) + 5 * 10.0 ** -rng.randint(2, 7)
        out.append(t)
        out.append(math.nextafter(t, math.inf))
        out.append(math.nextafter(t, -math.inf))
    return out


def random_doubles(rng: random.Random, n: int) -> list[float]:
    out = []
    for _ in range(n):
        c = rng.random()
        if c < 0.35:
            out.append(rng.uniform(-1000, 1000))
        elif c < 0.55:
            out.append(round(rng.uniform(0, 5000), rng.randint(0, 6)))
        elif c < 0.70:
            out.append(rng.uniform(-1, 1) * 10.0 ** rng.randint(-20, 20))
        elif c < 0.80:
            out.append(rng.randint(-10**6, 10**6) / rng.choice([2, 4, 8, 16, 100, 1000, 7, 3]))
        elif c < 0.9:
            x = from_bits(rng.getrandbits(64) - (1 << 63))
            out.append(x if math.isfinite(x) else 1.0)
        else:
            out.append(rng.gauss(0, 1) * 10.0 ** rng.randint(-3, 6))
    return out


def vec_round(rng, emit):
    xs = adversarial_doubles(rng)[:2500] + random_doubles(rng, 6000)
    for x in xs:
        for n in range(0, 7):
            emit({"k": "round", "x": D(x), "n": n, "o": D(round(x, n))})
        emit({"k": "round_int", "x": D(x), "o": str(round(x))})
    # round() on ints, negative ndigits, and ndigits=None semantics
    for v in range(-2000, 2000, 7):
        for n in (-3, -2, -1, 0):
            emit({"k": "round_intn", "v": v, "n": n, "o": str(round(v, n))})
    for x in (1234.5678, 15.0, 25.0, 35.0, -15.0, -25.0, 1250.0, 1e22):
        for n in (-1, -2, -3):
            emit({"k": "round_negn", "x": D(x), "n": n, "o": D(round(x, n))})


def quant(x: float, places: int, mode) -> tuple[str, dict | None]:
    q = Decimal(1).scaleb(-places)
    try:
        r = Decimal(str(x)).quantize(q, rounding=mode)
    except decimal.InvalidOperation:
        return "InvalidOperation", None
    return str(r), D(float(r))


def vec_quantize(rng, emit):
    xs = adversarial_doubles(rng)[:1500] + random_doubles(rng, 2500)
    for x in xs:
        for n in range(0, 7):
            for name, mode in (("half_up", ROUND_HALF_UP), ("half_even", ROUND_HALF_EVEN)):
                s, f = quant(x, n, mode)
                emit({"k": "quantize", "mode": name, "x": D(x), "n": n, "s": s, "f": f})
    # Decimal(str(x)) text itself (shortest repr), exercised through str
    for x in xs[:5000]:
        emit({"k": "decimal_str", "x": D(x), "s": str(Decimal(str(x)))})


def vec_repr(rng, emit):
    xs = adversarial_doubles(rng)[:2000] + random_doubles(rng, 15000)
    for _ in range(12000):  # random bit patterns incl. subnormals
        x = from_bits(rng.getrandbits(64) - (1 << 63))
        if math.isfinite(x):
            xs.append(x)
    xs += [math.inf, -math.inf, math.nan]
    for x in xs:
        emit({"k": "repr", "x": D(x), "s": repr(x), "str": str(x)})
    for i in range(-330, 310):  # power-of-ten boundaries
        for f in (1.0, 1.5, 9.999999999999999):
            try:
                x = float(f"{f}e{i}")
            except OverflowError:
                continue
            emit({"k": "repr", "x": D(x), "s": repr(x), "str": str(x)})


def vec_parse(rng, emit):
    texts = ["0", "-0", "+1", "1.", ".5", "1e5", "1E5", "1e-5", "  12.5  ", "\t7\n", "1_000", "1__0", "_1",
             "1_", "1,5", "", " ", "abc", "inf", "-inf", "Infinity", "+INF", "nan", "NaN", "-nan", "1e", "e5",
             "0x10", "1e400", "-1e400", "1e-400", "4.9e-324", "2.4703282292062327e-324", "2.4703282292062328e-324",
             "٣.١٤", "１２３", "1.0.0", "--1", "+-1", "0.1e1_0", "1_0e1_0", "9007199254740993", "0.30000000000000004",
             "123456789012345678901234567890", "0e999", "-0.0", "1e+3", "5e-324", "1.7976931348623157e308",
             "1.7976931348623159e308", "  ", "\u00a01", "1\u2003", "1\x00", "NAN", "iNf", "infinit", "infinity",
             "1_000.000_1", "1e1_0", "0.0000001", "-.5e-3"]
    for x in adversarial_doubles(rng)[:1000] + random_doubles(rng, 3000):
        texts.append(repr(x))
        texts.append(f"{x:.2f}")
        texts.append(f"{x:.17g}")
        texts.append(f"{x:.3e}")
    for t in texts:
        try:
            v = float(t)
            emit({"k": "parse", "t": t, "o": D(v)})
        except ValueError:
            emit({"k": "parse", "t": t, "o": None})
        except OverflowError:  # never raised for str, kept for safety
            emit({"k": "parse", "t": t, "o": None})


def vec_divmod(rng, emit):
    ints = [0, 1, -1, 2, -2, 3, -3, 7, -7, 10, -10, 12, -12, 100, -100, 2**31, -2**31, 2**62, -2**62, 2**63 - 1, -2**63]
    ints += [rng.randint(-10**9, 10**9) for _ in range(300)]
    for a in ints:
        for b in ints:
            if len(ints) > 60 and rng.random() < 0.9:
                continue
            if b == 0:
                emit({"k": "idivmod", "a": a, "b": b, "q": "ZeroDivisionError", "r": "ZeroDivisionError"})
            else:
                emit({"k": "idivmod", "a": a, "b": b, "q": str(a // b), "r": str(a % b)})
    fl = adversarial_doubles(rng)[:400] + random_doubles(rng, 4000) + [math.inf, -math.inf, math.nan]
    for _ in range(30000):
        a, b = rng.choice(fl), rng.choice(fl)
        try:
            q = a // b
            r = a % b
            dm = divmod(a, b)
            emit({"k": "fdivmod", "a": D(a), "b": D(b), "q": D(q), "r": D(r), "dq": D(dm[0]), "dr": D(dm[1])})
        except ZeroDivisionError:
            emit({"k": "fdivmod", "a": D(a), "b": D(b), "q": "ZeroDivisionError"})
    for _ in range(20000):  # int // float, float % int mixes
        a, b = rng.randint(-1000, 1000), rng.choice(fl)
        try:
            emit({"k": "mixdiv", "a": a, "b": D(b), "q": D(a // b), "r": D(a % b)})
        except ZeroDivisionError:
            emit({"k": "mixdiv", "a": a, "b": D(b), "q": "ZeroDivisionError"})
    for _ in range(5000):  # true division (the engine's x / y)
        a, b = rng.choice(fl), rng.choice(fl)
        try:
            emit({"k": "truediv", "a": D(a), "b": D(b), "o": D(a / b)})
        except ZeroDivisionError:
            emit({"k": "truediv", "a": D(a), "b": D(b), "o": "ZeroDivisionError"})


def vec_int_floor_ceil(rng, emit):
    xs = adversarial_doubles(rng) + random_doubles(rng, 8000) + [math.inf, -math.inf, math.nan, 2.0**63, -2.0**63, 1e19, -1e19]
    for x in xs:
        for name, fn in (("int", int), ("floor", math.floor), ("ceil", math.ceil), ("trunc", math.trunc)):
            try:
                emit({"k": name, "x": D(x), "o": str(fn(x))})
            except (ValueError, OverflowError) as e:
                emit({"k": name, "x": D(x), "o": type(e).__name__})


def vec_sum(rng, emit):
    for _ in range(12000):
        n = rng.choice([0, 1, 2, 3, 5, 10, 50, 300])
        mode = rng.random()
        if mode < 0.4:
            xs = [round(rng.uniform(0, 80), 2) for _ in range(n)]
        elif mode < 0.7:
            xs = [rng.uniform(-1, 1) * 10.0 ** rng.randint(-8, 8) for _ in range(n)]
        elif mode < 0.85:
            xs = [rng.choice([0.1, 0.2, 0.3, 1e16, -1e16, 1.0, -0.0, 0.0, 1e-16]) for _ in range(n)]
        else:
            xs = [rng.choice([rng.randint(-50, 50), round(rng.uniform(0, 9), 3)]) for _ in range(n)]
        xs = [x if isinstance(x, int) else x for x in xs]
        naive = 0
        for x in xs:
            naive += x
        emit({"k": "sum", "xs": [D(float(x)) if isinstance(x, float) else x for x in xs],
              "o": D(float(sum(xs))) if isinstance(sum(xs), float) else {"i": str(sum(xs))},
              "naive": D(float(naive)) if isinstance(naive, float) else {"i": str(naive)}})
    for xs in ([-0.0], [-0.0, -0.0], [0.0, -0.0], [], [1e308, 1e308], [1e308, 1e308, -1e308], [math.inf, -math.inf],
               [math.inf, 1.0], [math.nan, 1.0], [1.0, math.nan]):
        s = sum(xs)
        emit({"k": "sum", "xs": [D(x) for x in xs], "o": D(float(s)) if isinstance(s, float) else {"i": str(s)},
              "naive": None})
    # sum of bools and mixed int/float (the engine sums booleans: sum(m["counted"] ...))
    for _ in range(3000):
        n = rng.randint(0, 40)
        bs = [rng.random() < 0.5 for _ in range(n)]
        emit({"k": "sum_bool", "xs": bs, "o": str(sum(bs)), "div12": D(round(sum(bs) / 12.0, 4))})


def iso(d: dt.date) -> str:
    return d.isoformat()


def vec_dates(rng, emit):
    base = [dt.date(2020, 2, 29), dt.date(2023, 1, 31), dt.date(2024, 2, 29), dt.date(2023, 12, 31), dt.date(2000, 2, 29),
            dt.date(1900, 2, 28), dt.date(2100, 2, 28), dt.date(1, 1, 1), dt.date(9999, 12, 31), dt.date(2023, 7, 31),
            dt.date(2024, 8, 9), dt.date(2023, 3, 31), dt.date(2023, 5, 31)]
    base += [dt.date.fromordinal(rng.randint(1, 3652059)) for _ in range(300)]
    base += [dt.date(rng.randint(1990, 2040), rng.randint(1, 12), 1) for _ in range(300)]
    for d in base:
        y, m = d.year, d.month
        emit({"k": "monthrange", "y": y, "m": m, "o": list(calendar.monthrange(y, m))})
        emit({"k": "isoweekday", "d": iso(d), "o": [d.isoweekday(), d.weekday(), d.toordinal()]})
        emit({"k": "isocalendar", "d": iso(d), "o": list(d.isocalendar())})
        for n in (-400, -366, -35, -31, -7, -1, 0, 1, 6, 7, 13, 14, 28, 30, 31, 365, 366, 1000):
            try:
                emit({"k": "date_add", "d": iso(d), "n": n, "o": iso(d + dt.timedelta(days=n))})
            except OverflowError:
                emit({"k": "date_add", "d": iso(d), "n": n, "o": "OverflowError"})
        for ny, nm, nd in ((y, m, 29), (y, m, 30), (y, m, 31), (y + 1, m, d.day), (y, 12, d.day), (y, 2, d.day),
                           (y, m, 1), (y, 13, 1), (y, 0, 1), (y, m, 0), (0, m, 1), (10000, 1, 1), (y, m, d.day)):
            try:
                o = iso(dt.date(ny, nm, nd))
            except ValueError:
                o = "ValueError"
            try:
                o2 = iso(d.replace(year=ny, month=nm, day=nd))
            except ValueError:
                o2 = "ValueError"
            emit({"k": "date_make", "y": ny, "m": nm, "d": nd, "o": o, "replace_from": iso(d), "o_replace": o2})
    for _ in range(4000):
        a, b = rng.choice(base), rng.choice(base)
        emit({"k": "date_diff", "a": iso(a), "b": iso(b), "o": [(b - a).days, a < b, a == b]})
    texts = ["2023-01-31", "2023-1-31", "20230131", "2023-W05-2", "2023-W05", "2023-02-29", "2024-02-29", "0000-01-01",
             "2023-01-31T00:00:00", "2023-01-31 ", " 2023-01-31", "2023/01/31", "2023-13-01", "2023-00-10", "",
             "2023-01-31T12:30:00Z", "٢٠٢٣-٠١-٣١", "9999-12-31", "0001-01-01", "2023-366", "2023-W53-7", "2020-W53-7"]
    for t in texts:
        try:
            o = iso(dt.date.fromisoformat(t))
        except ValueError:
            o = "ValueError"
        # The engine only calls date.fromisoformat(str(s)[:10]); datetime.fromisoformat/strptime are not ported.
        emit({"k": "date_parse", "t": t, "o": o})
    for y in range(1900, 2101):  # month-end table for every year, used by measuring-date logic
        emit({"k": "month_ends", "y": y, "o": [list(calendar.monthrange(y, m)) for m in range(1, 13)], "leap": calendar.isleap(y)})


def vec_sort(rng, emit):
    for _ in range(6000):
        n = rng.randint(0, 40)
        kind = rng.choice(["int", "float", "str", "tuple", "negzero"])
        if kind == "int":
            keys = [rng.randint(0, 5) for _ in range(n)]
        elif kind == "float":
            keys = [round(rng.uniform(0, 3), 1) for _ in range(n)]
        elif kind == "negzero":
            keys = [rng.choice([0.0, -0.0, 1.0, -1.0, 0]) for _ in range(n)]
        elif kind == "str":
            keys = [rng.choice(["a", "B", "b", "Z", "z", "é", "e", "E1", "e1", "10", "9", "", " ", "A", "\u00c9", "e\u0301"]) for _ in range(n)]
        else:
            keys = [[rng.randint(0, 3), rng.choice(["x", "y", "X"])] for _ in range(n)]
        idx = list(range(n))
        key = (lambda i: tuple(keys[i])) if kind == "tuple" else (lambda i: keys[i])
        for rev in (False, True):
            emit({"k": "sort", "kind": kind, "reverse": rev,
                  "keys": [D(k) if isinstance(k, float) else k for k in keys],
                  "o": sorted(idx, key=key, reverse=rev)})
        if n:
            emit({"k": "minmax", "kind": kind,
                  "keys": [D(k) if isinstance(k, float) else k for k in keys],
                  "min": min(idx, key=key), "max": max(idx, key=key)})
    fl = [0.0, -0.0, 1.0, math.nan, -1.0, 2.0]
    for _ in range(3000):
        xs = [rng.choice(fl) for _ in range(rng.randint(1, 6))]
        emit({"k": "minmax_float", "xs": [D(x) for x in xs], "min": D(min(xs)), "max": D(max(xs)),
              "min2": D(min(xs[0], xs[-1])), "max2": D(max(xs[0], xs[-1]))})


def vec_strings(rng, emit):
    samples = ["ga", "Ga", "GA", " ga ", "ǆ", "ß", "ŉ", "ǰ", "İ", "ı", "Σ", "ς", "σ", "ΑΣ", "ﬁ", "ﬃ", "é", "É", "e\u0301",
               "\u00a0GA\u00a0", "\u2003GA", "\u200bGA", "\u3000GA\u3000", "\u0085GA", "\ufeffGA", "GA-001", "ga-001\t", "straße",
               "ǅ", "ᾳ", "ΐ", "ա", "և", "Ⅷ", "ⅷ", "\u1680x", "\x1cx\x1f", "x\x1d", "ΌΣ", "ǈ", "ꭰ", "ꙋ"]
    pool = [chr(c) for c in range(0x20, 0x2FF)] + [chr(c) for c in range(0x370, 0x5FF)] + list("ßŉǰΐΰ")
    for _ in range(3000):
        samples.append("".join(rng.choice(pool) for _ in range(rng.randint(0, 8))))
    for s in samples:
        # Only upper() and strip() are used by the engine (headcount.row_state); lower()/casefold()/title()
        # are context sensitive (final sigma) and deliberately out of scope for the port.
        emit({"k": "str", "s": s, "upper": s.upper(), "strip": s.strip(), "isspace": s.isspace(), "len": len(s)})
    cps = [chr(c) for c in (0x41, 0x61, 0x7a, 0xe9, 0xc9, 0x131, 0x130, 0x3a3, 0x3c3, 0x3c2, 0x1c5, 0x2160, 0x10400, 0x10428, 0x1e900, 0xff21)]
    for _ in range(8000):
        a = "".join(rng.choice(cps + list("abAB19 -")) for _ in range(rng.randint(0, 5)))
        b = "".join(rng.choice(cps + list("abAB19 -")) for _ in range(rng.randint(0, 5)))
        emit({"k": "strcmp", "a": a, "b": b, "lt": a < b, "eq": a == b, "cmp": (a > b) - (a < b)})
    # code point (not UTF-16 unit) ordering: astral vs BMP-high
    emit({"k": "strcmp", "a": "\U00010000", "b": "\uffff", "lt": "\U00010000" < "\uffff", "eq": False, "cmp": ("\U00010000" > "\uffff") - ("\U00010000" < "\uffff")})
    emit({"k": "strcmp", "a": "\ue000", "b": "\U00010000", "lt": "\ue000" < "\U00010000", "eq": False, "cmp": ("\ue000" > "\U00010000") - ("\ue000" < "\U00010000")})
    # exhaustive case-mapping table for every code point whose result differs from identity
    table = []
    for c in range(0x110000):
        if 0xD800 <= c <= 0xDFFF:
            continue
        ch = chr(c)
        u = ch.upper()
        if u != ch:
            table.append([c, [ord(x) for x in u]])
    emit({"k": "case_table", "table": table})
    ws = [c for c in range(0x110000) if not (0xD800 <= c <= 0xDFFF) and chr(c).isspace()]
    emit({"k": "space_table", "cps": ws})
    emit({"k": "unicode_version", "v": __import__("unicodedata").unidata_version})



def vec_int_parse(rng, emit):
    texts = ["0", "-0", "+5", "-5", "15", " 15 ", "\t7\n", "007", "00015", "1_0", "1__0", "_1", "1_", "1.5", "1e3", "", " ", "abc", "0x10", "١٥", "٣", "-٣",
             "1 5", "--1", "+-1", "٠٣", "99999999999999999999", "-99999999999999999999", "1_000_000", "\u00a07\u00a0", "5\x00", "+", "-", "1_2_3",
             "+٧", "\u2003-8", "١_٥", "१५", "๑๕", "①", "²", "٣.٠"]
    for t in texts:
        try:
            emit({"k": "int_parse", "t": t, "o": str(int(t))})
        except ValueError:
            emit({"k": "int_parse", "t": t, "o": None})

GENERATORS = [vec_int_parse, vec_round, vec_quantize, vec_repr, vec_parse, vec_divmod, vec_int_floor_ceil, vec_sum, vec_dates, vec_sort, vec_strings]


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    buf = io.BytesIO()
    meta = {"k": "meta", **oracle.stamp(), "seed": seed, "decimal_prec": decimal.getcontext().prec,
            "decimal_impl": decimal.__name__}
    count = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        def emit(o: dict) -> None:
            nonlocal count
            count += 1
            gz.write(json.dumps(o, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n")
        emit(meta)
        for g in GENERATORS:
            g(rng, emit)
    print(f"{count} vectors, {len(buf.getvalue()) / 1e6:.2f} MB", file=sys.stderr)
    return buf.getvalue()


def main() -> int:
    oracle.require()
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--check", action="store_true", help="fail if the committed file differs from a fresh export")
    a = ap.parse_args()
    data = build(a.seed)
    if a.check:
        if not a.out.exists() or a.out.read_bytes() != data:
            print("STALE: primitives goldens differ from a fresh export", file=sys.stderr)
            return 1
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
