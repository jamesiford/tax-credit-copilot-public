"""Pool sizing that can differ by platform. [09]

The constants in `fabric_warehouse.py` were measured against the Fabric Warehouse (a link is dead
after about 60 seconds idle). Nothing has measured Azure SQL, so its default is the same until a
live check says otherwise; `WAREHOUSE_POOL_MAX_*` overrides either platform without a code change.
"""
from __future__ import annotations

from config import get_settings


def max_age_s(default: int) -> int:
    """How long an idle link is trusted: the override, else the caller's measured default."""
    override = get_settings().platform.pool_max_age_s
    return default if override is None else override


def max_idle(default: int) -> int:
    """How many idle links the process keeps: the override, else the caller's default."""
    override = get_settings().platform.pool_max_idle
    return default if override is None else override
