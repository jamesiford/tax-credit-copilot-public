"""Input pools for ``export_gold.py``: the values a Gold projection is handed, hand-picked for their edges plus seeded random ones.

Everything here is a plain Python value (``str``, ``int``, ``float``, ``Decimal``, ``bool``, ``None``, ``date``, ``datetime``); the
exporter records each call's arguments with ``golden_rec.enc`` so the C# replay can rebuild the same types.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

NAN = float("nan")
INF = float("inf")


def dec_inputs(rng: random.Random) -> list:
    """Everything ``_dec`` is asked to quantize: ties, signs, magnitudes at the 28-digit edge, specials, and non-numbers."""
    pool: list = [
        None, "", 0, 1, -1, 7, 0.0, -0.0, 1.5, 0.1 + 0.2, 2.675, 1.005, 0.285, 1.115, 8.345, 8.355, 0.125, 0.375, 0.625, -0.125, 5e-324,
        1e-7, 1e-5, 1e-4, 0.0001, 0.00005, 0.00015, 0.00025, 1e15, 1e16, 1e22, 1e23, 1e27, 1e28, 1.7976931348623157e308, -1e27, 123456789012345678.9,
        "1972.36", "68.58", "0.005", "0.015", "0.025", "0.035", "-0.005", "-0.015", "0.00005", "0.00015", "0.00025", "0.0001", "1E+2", "1e-3", "-0.001",
        "  7.255 ", "1_000.125", "+5", ".5", "5.", "-.5e1", "0x10", "abc", "1,5", "1.2.3", "--1", " ", "NaN", "nan", "-nan", "+NaN", "nan12", "nan007",
        "nan000", "sNaN", "-sNaN", "inf", "-inf", "Infinity", "-Infinity", "1e5", "1E-30", "0E+5", "-0", "-0.0", "-0.00",
        "9999999999999999999999999.99", "99999999999999999999999999.99", "999999999999999999999999999.99", "1" + "0" * 26 + ".5", "1" + "0" * 27,
        "9999999999999999999999999999", "99999999999999999999999999999", "0.00000000000000000000000000001", "123456789.123456789123456789",
        True, False, 10**18, 10**26, 10**27, 10**28, 10**30, -(10**27), -(10**28), 2**64, -(2**70),
        NAN, INF, -INF,
        D("0.005"), D("0.015"), D("-0.005"), D("1E+2"), D("1E+25"), D("1E+26"), D("1E+27"), D("-0.00"), D("0E+5"), D("0E-30"), D("1E-30"), D("100.000"),
        D("1.23456789012345678901234567890"), D("12345678901234567890123456.785"), D("12345678901234567890123456.795"), D("99999999999999999999999999.995"),
        D("NaN"), D("-NaN"), D("NaN12"), D("sNaN"), D("Infinity"), D("-Infinity"),
        date(2023, 1, 1), datetime(2023, 1, 1, 5, 6, 7),
    ]
    for _ in range(260):
        k = rng.randint(0, 5)
        mag = 10.0 ** rng.randint(-8, 12)
        x = rng.uniform(-1, 1) * mag
        if k == 0:
            pool.append(x)
        elif k == 1:
            pool.append(round(x, rng.randint(0, 5)))
        elif k == 2:
            pool.append(f"{x:.{rng.randint(0, 6)}f}")
        elif k == 3:
            pool.append(f"{rng.randint(-10**7, 10**7) / 1000:.3f}")
        elif k == 4:
            pool.append(D(rng.randint(-10**9, 10**9)).scaleb(-rng.randint(0, 8)))
        else:
            pool.append(rng.randint(-10**6, 10**6))
    return pool


def day_inputs(rng: random.Random) -> list:
    """Everything ``_day`` is asked to turn into a date, including the shapes ``date.fromisoformat`` accepts and refuses."""
    pool: list = [
        None, "", date(2023, 1, 1), date(2024, 2, 29), date(1, 1, 1), date(9999, 12, 31), datetime(2023, 12, 31, 23, 59, 59),
        datetime(2023, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc), datetime(2024, 2, 29, 0, 0), datetime(2023, 6, 1, 12, tzinfo=timezone(timedelta(hours=-5, minutes=-30))),
        "2023-01-01", "2023-01-01T10:00:00", "2023-01-01 10:00:00", "2023-01-01Z", "2023-01-01garbage", "2024-02-29", "2023-02-29", "2023-02-28", "2023-13-01",
        "2023-00-10", "2023-04-31", "2023-12-32", "0001-01-01", "0000-01-01", "9999-12-31", "20230101", "2023W011", "2023-W01-1", "2023-W53-1", "2020-W53-7",
        "2023-W01", "2023-01", "2023", "23-01-01", "2023/01/01", "01/02/2023", " 2023-01-01", "2023-1-1", "2023-01-1", "abcdefghij", "None", "N", " ", "\t",
        "2023-01-01extra-long-text", 20230101, 2023, 0, -1, 1.5, 20230101.0, True, False, D("20230101"), D("1E+9"), NAN, INF,
        "2019-12-30", "2021-01-03", "2026-12-31", "1999-12-31", "2000-02-29", "1900-02-29", "2100-02-29", "2023-11-31",
    ]
    for _ in range(300):
        d0 = date(1990, 1, 1) + timedelta(days=rng.randint(0, 20000))
        k = rng.randint(0, 3)
        pool.append(d0.isoformat() if k == 0 else d0.strftime("%Y%m%d") if k == 1 else d0 if k == 2 else d0.isoformat() + "T00:00:00")
    return pool


def flag_inputs() -> list:
    return [None, True, False, 0, 1, -1, 2, 0.0, -0.0, 0.5, NAN, INF, "", "0", "False", " ", D("0"), D("0.00"), D("-0.00"), D("NaN"), D("0.01"),
            [], [0], {}, {"a": 1}, date(2023, 1, 1), "x", 10**30]


def account_ids() -> list:
    return [None, 0, 1, 1001, 2000, -1, 10**20, 2**63, -(2**63) - 1]


def employee_ids() -> list[str]:
    return ["E1", "", "0", "48685377", "E 1", "É1", "e\u0301", "\u4e2d\u6587", "a\0b", "\U00010000x", "x" * 200, "\n", "'quote'", '"dq"',
            "None", "NaN", "\ud800", "a\udfffb"]


def unicode_ids() -> list[str]:
    return ["E001", "E\u00e9", "\u0130stanbul", "\u4e2d", "a\0", "\U0001f600"]
