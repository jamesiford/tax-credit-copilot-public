"""Golden vectors for ``json.loads`` / ``json.dumps`` (stage DS2).

Each vector is one text with the oracle's answer: either the re-serialised tree under two ``dumps`` configurations
(which also proves int versus float, key order and big ints survive) or the exception type and message. Inputs are
handcrafted edge cases, every rule-pack and registry file under ``backend/rules``, and seeded mutations of those
(deleted, duplicated, swapped and replaced characters) so malformed-document messages and offsets are covered.

Usage: python parity/export_json.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "json.jsonl.gz"
SEED = 20261114

HANDCRAFTED = [
    "null", "true", "false", "0", "-0", "0.0", "-0.0", "35", "35.0", "1e2", "1E2", "1e+2", "1e-2", "1.5e3", "-1.5E-3",
    "12345678901234567890", "-12345678901234567890", "9223372036854775807", "9223372036854775808", "-9223372036854775808",
    "-9223372036854775809", "1e999", "-1e999", "1e-999", "NaN", "Infinity", "-Infinity", "[NaN, Infinity, -Infinity]",
    "01", "-", "-a", "1.", "1.e2", ".5", "+1", "1e", "1e+", "1e5.5", "0x10", "00", "1_000", "٣",
    '""', '"a"', '"\\u00e9"', '"\\ud83d\\ude00"', '"\\ud83d"', '"\\ude00"', '"\\ud83d\\u0041"', '"\\ud83dx"', '"\\u12"', '"\\u12G4"',
    '"\\x"', '"\\/"', '"\\b\\f\\n\\r\\t"', '"tab\there"', '"nl\nhere"', '"unterminated', '"a\\', '"\x7f"', '"é"', '"\U0001F600"',
    "[]", "[ ]", "[1]", "[1,]", "[,1]", "[1 2]", "[1,2", "[", "]", "[[[]]]", '[1, "a", null, true, 1.0, 2]',
    "{}", "{ }", '{"a":1}', '{"a":1,}', '{"a" 1}', '{"a":}', '{a:1}', "{'a':1}", '{"a":1 "b":2}', '{"a":1,"a":2}',
    '{"a":1,"b":2,"a":3}', '{"b":1,"a":2}', '{"é":1,"a":2,"\U0001F600":3,"\uffff":4}', '{"":1}', '{"a":{"b":{"c":[1,2,{"d":null}]}}}',
    "", " ", "  \n\t\r ", "nul", "nulL", "tru", "[1]x", "{} {}", "1 2", "\ufeff[1]", "\ufeff", "[1]\n", " [1] ",
    "\U0001F600", '["\U0001F600", x]', '{"\U0001F600": x}', '"\U0001F600\n', "\n\n[1,\n\n x]", "-Infinit", "-Infinity1", "Infinit",
    "1" * 4300, "1" * 4301, "-" + "1" * 4300, "-" + "1" * 4301, "[" + "1" * 4301 + "]",
    "123456789012345678901234567890.5", "0.1", "0.30000000000000004", "1e22", "1e23", "123456789.123456789e-5", "5e-324", "2e-324", "1.7976931348623157e308", "1.7976931348623159e308",
]


def outcome(text: str) -> dict:
    try:
        tree = json.loads(text)
    except json.JSONDecodeError as e:
        return {"err": "JSONDecodeError", "msg": str(e)}
    except Exception as e:  # ValueError for the int digit limit; anything else is a finding
        return {"err": type(e).__name__, "msg": str(e)}
    return {
        "plain": json.dumps(tree),
        "sorted": json.dumps(tree, sort_keys=True, separators=(",", ":")),
    }


def corpus(seed: int) -> list[str]:
    texts = list(HANDCRAFTED)
    files = sorted((ROOT / "backend" / "rules").rglob("*.json"))
    docs = [p.read_text(encoding="utf-8") for p in files]
    texts.extend(docs)
    rng = random.Random(seed)
    alphabet = list('{}[]",:\\ \n\t-+.eE0123456789abnrtuNIf\u00e9\U0001F600\x00\x1f') + ["null", "true", "NaN", "\\u", "\\ud800"]
    small = [d for d in docs if len(d) < 4000] or docs
    for _ in range(6000):
        base = rng.choice(small if rng.random() < 0.7 else HANDCRAFTED)
        for _ in range(rng.randint(1, 3)):
            if not base:
                base = rng.choice(alphabet)
                continue
            i = rng.randrange(len(base))
            op = rng.randrange(5)
            if op == 0:
                base = base[:i] + base[i + 1:]
            elif op == 1:
                base = base[:i] + rng.choice(alphabet) + base[i:]
            elif op == 2:
                base = base[:i] + rng.choice(alphabet) + base[i + 1:]
            elif op == 3:
                base = base[:i]
            else:
                j = rng.randrange(len(base))
                a, b = sorted((i, j))
                base = base[:a] + base[b:b + 1] + base[a + 1:b] + base[a:a + 1] + base[b + 1:]
        texts.append(base)
    return texts


def build(seed: int) -> bytes:
    lines = [json.dumps({"k": "meta", "seed": seed, **oracle.stamp()}, separators=(",", ":"))]
    for text in corpus(seed):
        lines.append(json.dumps({"k": "json", "in": text, **outcome(text)}, separators=(",", ":"), ensure_ascii=True))
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
        return 0 if args.out.exists() and args.out.read_bytes() == data else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
