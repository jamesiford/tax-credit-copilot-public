"""Runtime configuration the calculation reads.

`get_fiscal_year_end_month` used to live in `api/settings.py` behind a mutable
PUT endpoint — one global accounting year for every client at once, editable at
runtime, and read by the statutory path. A router is the wrong home for
configuration the engine depends on, and a global is the wrong shape for a fact
that belongs to a client.

It is a constant here because the real answer lives elsewhere:
`infrastructure/payroll/fiscal_source.py` resolves a client's actual window from
their own `EntityFiscalYearRules`. Wiring that into month bucketing changes
figures for every non-calendar filer, which is gated on PILOT-07 — see
`domain/calculation/fiscal.py`.
"""
from __future__ import annotations

import os
import re

#: Calendar year. The only value the deleted setting ever returned in practice.
DEFAULT_FISCAL_YEAR_END_MONTH = 12


def get_fiscal_year_end_month() -> int:
    """The fiscal year-end month used for month bucketing (1-12; 12 = calendar)."""
    return DEFAULT_FISCAL_YEAR_END_MONTH


# --- Warehouse schema names (Platform v2, D11) ------------------------------
#
# The two schemas the application owns. They are configuration so a customer
# can host them under their own names; the defaults are what DDL v2.0 creates.
# They are interpolated into SQL text (a schema cannot be a bound parameter),
# so anything that is not a plain identifier is refused at import rather than
# reaching a statement.

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

DEFAULT_GOLD_SCHEMA = "tcc_gold"
DEFAULT_OPS_SCHEMA = "tcc_ops"


def schema_name(env_var: str, default: str) -> str:
    """Read a schema name from the environment, refusing a non-identifier."""
    value = (os.getenv(env_var) or default).strip()
    if not _IDENTIFIER.match(value):
        raise ValueError(
            f"{env_var}={value!r} is not a plain SQL identifier; schema names are "
            f"interpolated into statements and must match {_IDENTIFIER.pattern}"
        )
    return value


#: The read schema: every figure a screen shows.
GOLD_SCHEMA = schema_name("GOLD_SCHEMA", DEFAULT_GOLD_SCHEMA)

#: Operational and provenance tables: runs, overrides, claims, findings, artifacts.
OPS_SCHEMA = schema_name("OPS_SCHEMA", DEFAULT_OPS_SCHEMA)

#: The source schema: the customer's payroll tables in the Fabric Lakehouse
#: (`data/source/`, `DATA_SOURCE=lakehouse`). This one is a parameter rather
#: than a fixed name on purpose (D14) — a customer's own Fabric lakehouse may
#: already use a schema name of its own (an overlay sets `SOURCE_SCHEMA`
#: accordingly), and the public default stands in for one that does not.
DEFAULT_SOURCE_SCHEMA = "tcc_source"

SOURCE_SCHEMA = schema_name("SOURCE_SCHEMA", DEFAULT_SOURCE_SCHEMA)
