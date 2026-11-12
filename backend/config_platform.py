"""Which SQL platform holds `tcc_ops` and `tcc_gold`, and how its connections are pooled. [09]

`fabric` (the default) is the Fabric Warehouse. `azure_sql` is an Azure SQL Database reached over
the same ODBC driver and the same Entra token. The pool overrides are unset by default: the Fabric
constants in `fabric_warehouse.py` stay in force until somebody measures the other platform.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from config_values import choice as _choice

PLATFORMS = ("fabric", "azure_sql")


@dataclass(frozen=True)
class PlatformSettings:
    """The platform and the optional pool overrides (None = the platform's own default)."""

    platform: str = "fabric"
    pool_max_idle: int | None = None
    pool_max_age_s: int | None = None

    @property
    def is_azure_sql(self) -> bool:
        return self.platform == "azure_sql"


def parse_platform(environ: Mapping[str, str]) -> PlatformSettings:
    """`WAREHOUSE_PLATFORM` and the two pool overrides; every one is optional."""
    def optional(name: str, minimum: int) -> int | None:
        raw = (environ.get(name) or "").strip()
        try:
            return max(minimum, int(raw)) if raw else None
        except ValueError:
            return None

    return PlatformSettings(
        platform=_choice(environ, "WAREHOUSE_PLATFORM", PLATFORMS, "fabric"),
        pool_max_idle=optional("WAREHOUSE_POOL_MAX_IDLE", 1),
        pool_max_age_s=optional("WAREHOUSE_POOL_MAX_AGE_SECONDS", 5),
    )
