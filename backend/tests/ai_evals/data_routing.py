"""The data-routing eval: for a nuanced question, is the planned tool sequence the right one, and does the platform answer it as designed? [CH-16e]

A model plans; the platform decides whether the plan may run. This eval scores both halves offline, with no
model: each row records a question and the plan a good planner makes (or, for a refusal row, the plan a bad one
might), and the scorer

1. checks the tool sequence equals the expected one (fixed engine tools first, the catalog before a query, a
   lookup before a filter, nothing at all for a question the data cannot answer) and names no forbidden tool;
2. checks every tool is one a model may be offered;
3. RUNS each data step through the real capability over the shared two-client SQLite fixture, so "valid" means
   the specification passed the real validator and executed, and "refused" names the typed error code;
4. checks the lane (employee-level rows go to the person only), the cap flag and a catalog miss where the row says so.

It is the deterministic counterpart of the live routing eval: it cannot say what a model will plan, but it
can say what the platform does with the plan, and that the questions the product must handle each have a plan.
"""
from __future__ import annotations

import json
from typing import Any

from application.capabilities import catalog
from application.capabilities.invoke import CapabilityFailure, invoke
from bootstrap.channel_wiring import set_writer_entitlement
from bootstrap.data_wiring import set_data_query_service
from tests.ai_evals.harness import HERE, EvalResult
from tests.data_caps_fixture import Writers, make_service, person

SUITE = "data_routing"
FIXTURE_CLIENT = 2002
DATA_TOOLS = ("data_catalog", "data_query", "data_distinct_values")


def load_rows() -> list[dict[str, Any]]:
    lines = (HERE / "datasets" / f"{SUITE}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _offered() -> set[str]:
    """What a model may name: built reads and previews, never a commit and never plumbing."""
    return {s.name for s in catalog.offered() if s.kind != catalog.WRITE_COMMIT and not {catalog.GATEWAY_LOCAL, catalog.INTERNAL} & set(s.tags)}


def _run(step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """`("ok", facts)` or `(<refusal code>, {})` for one planned data step, through the real capability."""
    args = dict(step.get("args", {}))
    if step["tool"] != "data_catalog":
        args["client_id"] = FIXTURE_CLIENT
    try:
        return "ok", invoke(step["tool"], args, person()).to_dict()["facts"]
    except CapabilityFailure as failure:
        return failure.body()["error"]["code"], {}


def _outcome(plan: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """The first refusal in the plan (the model would stop there), else ok; and the last data step's facts."""
    facts: dict[str, Any] = {}
    for step in plan:
        if step["tool"] not in DATA_TOOLS:
            continue
        code, facts = _run(step)
        if code != "ok":
            return code, {}
    return "ok", facts


def _problems(row: dict[str, Any]) -> list[str]:
    names = [step["tool"] for step in row["plan"]]
    problems = [] if names == row["expected"] else [f"planned {names}, expected {row['expected']}"]
    problems += [f"named forbidden {t}" for t in sorted(set(names) & set(row.get("forbidden", ())))]
    problems += [f"{t} is not a tool a model may name" for t in names if t not in _offered()]
    code, facts = _outcome(row["plan"])
    if code != (row.get("refusal") or "ok"):
        problems.append(f"platform answered {code}, expected {row.get('refusal') or 'ok'}")
    elif code == "ok":
        problems += _facts_problems(row, facts)
    return problems


def _facts_problems(row: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    found = []
    if "lane" in row and facts.get("audience") != row["lane"]:
        found.append(f"lane {facts.get('audience')}, expected {row['lane']}")
    if "truncated" in row and facts.get("truncated") is not row["truncated"]:
        found.append(f"truncated {facts.get('truncated')}, expected {row['truncated']}")
    if "catalog_hits" in row and facts.get("dataset_count") != row["catalog_hits"]:
        found.append(f"catalog hits {facts.get('dataset_count')}, expected {row['catalog_hits']}")
    return found


def score(rows: list[dict[str, Any]]) -> EvalResult:
    """Every row's plan, judged against the real catalog, validator and fixture."""
    set_data_query_service(make_service())
    set_writer_entitlement(Writers())
    try:
        judged = []
        for row in rows:
            found = _problems(row)
            judged.append((row["id"], not found, "; ".join(found) or "ok"))
    finally:
        set_data_query_service(None)
        set_writer_entitlement(None)
    failures = tuple(f"{rid}: {detail}" for rid, ok, detail in judged if not ok)
    return EvalResult(SUITE, "offline", sum(1 for _, ok, _ in judged if ok), len(judged), failures)
