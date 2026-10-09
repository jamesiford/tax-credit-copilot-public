"""One-off: prove the converted read paths answer from Gold, not the engine.

Every figure below is READ. Nothing here runs `run_min_max_method`.

    cd backend
    $env:PYTHONPATH="."; python tools/verify_gold_reads.py
"""
from __future__ import annotations

import time

from dotenv import load_dotenv

load_dotenv()

CLIENT = 1001
YEAR = 2023


def main() -> None:
    from application.queries.get_eligibility import GetEligibilityQuery
    from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
    from application.wiring import get_mediator
    from tests.certified import (
        CERTIFIED_EMPLOYEES,
        CERTIFIED_MIN_MAX_ELIGIBLE,
        CERTIFIED_PAY_PERIOD_ELIGIBLE,
    )

    mediator = get_mediator()

    began = time.perf_counter()
    population = mediator.send(GetEligibilityQuery(
        tax_year=YEAR, state="GA", account_id=CLIENT, limit=5,
    ))
    elapsed = (time.perf_counter() - began) * 1000

    print("=== who qualifies, from tcc_gold.employee_eligibility ===")
    print(f"run                  {population['run']['run_id']}")
    print(f"state                {population['calculation_state']}")
    print(f"employees evaluated  {population['employees_evaluated']:>7}  "
          f"expected {CERTIFIED_EMPLOYEES}")
    print(f"min_max eligible     {population['min_max_eligible']:>7}  "
          f"expected {CERTIFIED_MIN_MAX_ELIGIBLE}")
    print(f"pay_period eligible  {population['pay_period_eligible']:>7}  "
          f"expected {CERTIFIED_PAY_PERIOD_ELIGIBLE}")
    print(f"near the floor       {population['near_floor']:>7}")
    print(f"read in              {elapsed:>7.0f}ms")

    ok = (
        population["employees_evaluated"] == CERTIFIED_EMPLOYEES
        and population["min_max_eligible"] == CERTIFIED_MIN_MAX_ELIGIBLE
        and population["pay_period_eligible"] == CERTIFIED_PAY_PERIOD_ELIGIBLE
    )
    print(f"CERTIFIED FIGURES    {'REPRODUCED' if ok else 'MOVED — STOP'}")

    for method in ("min_max", "pay_period"):
        began = time.perf_counter()
        matrix = mediator.send(GetOneZeroMatrixQuery(
            tax_year=YEAR, state="GA", account_id=CLIENT, method=method,
        ))
        elapsed = (time.perf_counter() - began) * 1000
        print(f"\n=== one/zero {method}, from tcc_gold ===")
        print(f"state                {matrix['calculation_state']}")
        print(f"annual average       {matrix['annual_average']}")
        print(f"eligible employees   {matrix['eligible_employees']}")
        print(f"matrix rows          {matrix['matrix_rows']}")
        print(f"unit x FEIN rows     {matrix['units']}")
        print(f"contested months     {matrix['contested_months']}   "
              f"<- only run_method_summary can answer this")
        print(f"months               {len(matrix['months'])} "
              f"({matrix['months'][0]} .. {matrix['months'][-1]})")
        print(f"read in              {elapsed:.0f}ms")


if __name__ == "__main__":
    main()
