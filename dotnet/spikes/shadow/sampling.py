"""Interleaved reads preserve outages and drift in the planned denominator."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import statistics
import time
from typing import Callable

from catalogue import CASES, LIVE_EFFECTS
from safe_compare import compare_document


@dataclass(frozen=True)
class Marker:
    count: int
    maximum: object

    @property
    def usable(self) -> bool:
        return type(self.count) is int and self.count > 0 and self.maximum is not None


def unmeasured(reasons: list[str], repeats: int = 2) -> dict:
    return {case.group: {"planned": repeats, "eligible": 0, "attempted": 0, "paired": 0,
                         "completed": 0, "inconclusive": 0, "hash_matches": 0,
                         "semantic_matches": 0, "failed": 0,
                         "unmeasured_reasons": [*reasons, *sorted({item.effect + "-excluded" for item in CASES.values()
                             if item.group == case.group and item.effect not in LIVE_EFFECTS})]}
            for name, case in CASES.items() if name not in ("artifact", "export", "situation", "canonical")}


def paired(case: str, fetch: Callable, fingerprint: Callable, repeats: int = 2) -> dict:
    if repeats not in (1, 2):
        raise ValueError("sample-bound")
    count = Counter(planned=repeats, eligible=repeats)
    samples, timings, markers = [], {"python": [], "dotnet": []}, []
    started = time.monotonic()
    before, before_ms = _marker(fingerprint)
    previous = {}
    for ordinal in range(1, repeats + 1):
        count["attempted"] += 1
        replies = {}
        failures = []
        # Alternate which host goes first; do not retry failed observations.
        order = ("python", "dotnet") if ordinal % 2 else ("dotnet", "python")
        for host in order:
            sample_start = time.monotonic()
            try:
                if time.monotonic() - started > 90:
                    raise TimeoutError("window")
                replies[host] = fetch(host)
                timings[host].append({"sample": ordinal, "ms": round((time.monotonic() - sample_start) * 1000, 3),
                                      "outcome": "response"})
            except Exception:  # noqa: BLE001 - explicit failure retained without URL/driver exception text
                failures.append("transport-or-bound")
                timings[host].append({"sample": ordinal, "ms": round((time.monotonic() - sample_start) * 1000, 3),
                                      "outcome": "failed"})
        after, after_ms = _marker(fingerprint)
        stable = before is not None and after is not None and before == after
        markers.append({"kind": "account-count-max-modified-v1",
                        "verdict": "unchanged" if stable else "changed-or-unprovable",
                        "before_ms": before_ms, "after_ms": after_ms})
        if len(replies) == 2:
            count["paired"] += 1
            result = compare_document({"case": case, "expected": replies["python"],
                                       "actual": replies["dotnet"], "sample": ordinal})
            repeated = all(host not in previous or compare_document({
                "case": case, "expected": previous[host], "actual": replies[host]})["semantic_equal"]
                           for host in replies)
            successful = all(200 <= reply["status"] < 300 for reply in replies.values())
            if stable and repeated and successful and "verdict" not in result:
                count["completed"] += 1
                count["hash_matches"] += int(result["content_hash_equal"])
                count["semantic_matches"] += int(result["semantic_equal"])
                count["failed"] += int(not result["semantic_equal"])
            else:
                count["inconclusive"] += 1
                count["failed"] += int(not result["semantic_equal"] or not successful)
            samples.append(result)
            previous = replies
        else:
            count["inconclusive"] += 1
            count["failed"] += 1
            samples.append({"sample": ordinal, "verdict": "transport-or-bound", "failures": len(failures)})
        before = after
        before_ms = after_ms
    return {"route": CASES[case].route, **{key: count[key] for key in (
        "planned", "eligible", "attempted", "paired", "completed", "inconclusive",
        "hash_matches", "semantic_matches", "failed")}, "samples": samples,
        "markers": markers, "timings": timings,
        "combined_ms": round((time.monotonic() - started) * 1000, 3)}


def _marker(read: Callable) -> tuple[Marker | None, float]:
    started = time.monotonic()
    try:
        value = read()
        result = value if isinstance(value, Marker) and value.usable else None
    except Exception:  # noqa: BLE001 - unavailable source is inconclusive, never equality
        result = None
    return result, round((time.monotonic() - started) * 1000, 3)


def timing_summary(observations: list[dict]) -> dict:
    successes = [row["ms"] for row in observations if row["outcome"] == "response"]
    transport_failures = len(observations) - len(successes)
    http_failures = sum(row["outcome"] == "response" and not row.get("http_success", True) for row in observations)
    return {"attempted": len(observations), "responses": len(successes),
            "failures": transport_failures + http_failures,
            "transport_failures": transport_failures, "http_failures": http_failures,
            "median_scope": "all completed HTTP responses, including non-success",
            "median_ms": round(statistics.median(successes), 3) if successes else None,
            "tail": "unmeasured: too few independent samples",
            "p95_ms": None, "p99_ms": None}
