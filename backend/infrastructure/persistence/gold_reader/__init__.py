"""Reading `tcc_gold`. The screens' only source of figures. [RM-19: a package, one module per read model]

The counterpart to `warehouse_gold.GoldWriter`. A run writes; every read comes
here. No calculation happens on a page load — if a client has not been
calculated, that is an answer, not a reason to compute one.

Three states, and they are modelled rather than inferred:

  * **calculated**      a live run exists, and its rows are returned.
  * **not_calculated**  no live run exists. `run` is None and `items` is empty
                        BECAUSE NOTHING HAS RUN. Callers must render this as an
                        invitation to run the calculation.
  * **calculated, zero** a live run exists and legitimately produced no rows.
                        `run` is populated and `items` is empty.

The last two look identical on `total` alone, which is why `run` is the
discriminator and `calculation_state` says it out loud. Collapsing them puts
"this client has no payroll" on screen for a client nobody has assessed yet.

Money is returned as a STRING, never a float. JSON has no decimal type, and
`Decimal("12345678.91")` serialised as a JSON number comes back
`12345678.909999999`. Headcount is a measurement rather than money and stays a
float, which is the same split the Gold schema itself makes.

Layout. Every read is a `_stmt_*` function (SQL text and parameters, in the `stmt_*`
modules) and a method on `GoldReader` (in the `reads_*` modules, one class per group,
assembled in `reader`). Each statement is built once because it is issued two ways: on
its own, and inside a batch. A page was costing eight sequential round trips at a ~125ms
floor each, so the cost was the count of trips, not the work; and a batched read quietly
returning different rows from the individual one is the kind of fault that reaches a
filed return. One definition, two callers.

`columns` holds the column sets: `_MONEY_COLUMNS` and `_BOOL_COLUMNS` type a value by its
NAME, so a SQL aggregate must never borrow a BIT column's name, and a summed money alias
must be in `_MONEY_COLUMNS` (`test_no_aggregate_is_aliased_to_a_bit_column_name`).

Every name the old single module defined is re-exported here, so
`from infrastructure.persistence.gold_reader import ...` keeps working. Callers that
are not adapters depend on `application.gold_read_port.GoldReadPort`, not on this package.
"""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import (  # noqa: F401
    GOLD_SCHEMA,
    OPS_SCHEMA,
    STRANDED_RUN_MINUTES,
    FabricWarehouseConnection,
)
from infrastructure.persistence.gold_reader.columns import (  # noqa: F401
    _BOOL_COLUMNS,
    _CONNECTION_LOST_STATES,
    _MONEY_COLUMNS,
    UNIT_YEAR_MASTER_COLUMNS,
    Statement,
    _rows,
    _value,
)
from infrastructure.persistence.gold_reader.envelope import run_envelope  # noqa: F401
from infrastructure.persistence.gold_reader.reader import GoldReader  # noqa: F401
from infrastructure.persistence.gold_reader.stmt_drill import (  # noqa: F401
    _stmt_cohort_periods,
    _stmt_drill_periods,
    _stmt_drill_segments,
    _stmt_drill_verdicts,
)
from infrastructure.persistence.gold_reader.stmt_eligibility import (  # noqa: F401
    _ELIGIBILITY_DRIFT,
    _ELIGIBILITY_NEAR,
    _ELIGIBILITY_PIVOT,
    _ELIGIBILITY_STATUS,
    ELIGIBILITY_SORTS,
    _eligibility_filter,
    _near_params,
    _stmt_eligibility_matching,
    _stmt_eligibility_page,
    _stmt_eligibility_summary,
)
from infrastructure.persistence.gold_reader.stmt_risk import (  # noqa: F401
    _stmt_at_risk,
    _stmt_at_risk_counts,
    _stmt_proximity_candidates,
    _stmt_proximity_counts,
)
from infrastructure.persistence.gold_reader.stmt_run_summary import (  # noqa: F401
    _stmt_client_year_credit,
    _stmt_client_year_rows,
    _stmt_client_year_series,
    _stmt_method_summary,
    _stmt_month_totals,
    _stmt_onezero_matrix,
    _stmt_unit_fein_summary,
)
from infrastructure.persistence.gold_reader.stmt_runs import (  # noqa: F401
    _MANIFEST_COLUMNS,
    _stmt_latest_run,
    _stmt_run_in_flight,
)
from infrastructure.persistence.gold_reader.stmt_unit_people import (  # noqa: F401
    _EMPLOYEE_SORTS,
    _NEAR_SORTS,
    EMPLOYEE_FILTERS,
    NEAR_FILTERS,
    _order_by,
    _stmt_unit_employees,
    _stmt_unit_near_threshold,
)
from infrastructure.persistence.gold_reader.stmt_units import (  # noqa: F401
    _MONTH_COLUMNS,
    _stmt_credit_columns,
    _stmt_credit_grid,
    _stmt_month_summaries,
    _stmt_unit,
    _stmt_unit_grid,
    _stmt_unit_lifetime,
    _stmt_unit_months,
    _stmt_unit_totals,
    _stmt_unit_years,
    _stmt_unit_years_count,
    _unit_year_where,
)
