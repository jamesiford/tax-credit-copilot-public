"""Runtime configuration, and the ONE reader of the environment. [RM-20, D-142]

Everything else in `backend/` is handed a value, a typed section of `Settings`, or a
mapping that came from here. `tests/test_architecture_settings.py` fails on
`os.environ` / `os.getenv` anywhere else, so a setting cannot be read in a corner
nobody lists.

`get_settings()` re-reads the process environment on every call (a copy of about a
hundred strings), because the readers it replaced did the same on every call and
tests change the environment per test. A reader that cached before (the AI settings,
a module constant) still caches in its own module; this module adds no cache of its own.
A test that wants fixed values passes them to `override_settings` instead of editing
the process environment.

Sections are parsed on first use, not when `Settings` is built: a bad number in one
section must not stop a process that never reads that section, which is how the
scattered readers behaved. The parsers are in `config_sections.py`.

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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType

import data_map
from config_sections import (
    DataSourceSettings, IdentitySettings, ObservabilitySettings, PortfolioSettings, RuntimeSettings, StoresSettings, WarehouseSettings,
    WebIqSettings, parse_data_source, parse_identity, parse_observability, parse_portfolio, parse_runtime, parse_schema_name,
    parse_source_schema, parse_stores, parse_warehouse, parse_webiq,
)
from config_aliases import warn_deprecated, with_aliases
from config_limits import LimitSettings, parse_limits
from config_platform import PlatformSettings, parse_platform
from config_programs import ProgramSettings, parse_programs
from config_runs import RunSettings, parse_runs
from config_source_model import SourceModelSettings, parse_source_model

#: Calendar year. The only value the deleted setting ever returned in practice.
DEFAULT_FISCAL_YEAR_END_MONTH = 12


def get_fiscal_year_end_month() -> int:
    """The fiscal year-end month used for month bucketing (1-12; 12 = calendar)."""
    return DEFAULT_FISCAL_YEAR_END_MONTH


@dataclass(frozen=True, eq=False)
class Settings:
    """A frozen snapshot of the environment and the typed sections read from it.

    `environ` is for the parsers that must stay independent of this module because the
    orchestrator vendors them (AI, knowledge, gateway, deployment checks): the composition
    root hands them this mapping. Reading a variable by name from it elsewhere is what
    the sections exist to avoid.
    """

    environ: Mapping[str, str]

    @cached_property
    def runtime(self) -> RuntimeSettings:
        return parse_runtime(self.environ)

    @cached_property
    def observability(self) -> ObservabilitySettings:
        return parse_observability(self.environ)

    @cached_property
    def identity(self) -> IdentitySettings:
        return parse_identity(self.environ)

    @cached_property
    def data_source(self) -> DataSourceSettings:
        return parse_data_source(self.environ)

    @cached_property
    def portfolio(self) -> PortfolioSettings:
        return parse_portfolio(self.environ)

    @cached_property
    def source_model(self) -> SourceModelSettings:
        return parse_source_model(self.environ)

    @cached_property
    def platform(self) -> PlatformSettings:
        return parse_platform(self.environ)

    @cached_property
    def runs(self) -> RunSettings:
        return parse_runs(self.environ)

    @cached_property
    def limits(self) -> LimitSettings:
        return parse_limits(self.environ)

    @cached_property
    def programs(self) -> ProgramSettings:
        return parse_programs(self.environ)

    @cached_property
    def warehouse(self) -> WarehouseSettings:
        return parse_warehouse(self.environ)

    @cached_property
    def stores(self) -> StoresSettings:
        return parse_stores(self.environ)

    @cached_property
    def webiq(self) -> WebIqSettings:
        return parse_webiq(self.environ)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Settings from `environ`, or from the process environment when none is given."""
    source = os.environ if environ is None else environ
    warn_deprecated(source)
    return Settings(MappingProxyType(with_aliases(source)))


_override: Settings | None = None


def get_settings() -> Settings:
    """The overriding settings if a test installed some, else a fresh read of the environment."""
    return _override if _override is not None else load_settings()


def synthetic_environment() -> bool:
    """Whether this environment states that all of its data is generated. Unset is not synthetic."""
    return get_settings().runtime.data_classification == "synthetic"


def use_managed_identity(client_id: str) -> None:
    """Select a user-assigned managed identity for this process: the Azure SDK reads `AZURE_CLIENT_ID` when a credential is built.

    Here because this module is the one place that touches the process environment. Call it before anything builds a credential.
    """
    os.environ["AZURE_CLIENT_ID"] = client_id


def set_settings(settings: Settings | None) -> None:
    """Install fixed settings, or with `None` go back to reading the environment."""
    global _override
    _override = settings


@contextmanager
def override_settings(environ: Mapping[str, str]) -> Iterator[Settings]:
    """Run a block against fixed settings built from `environ`, then restore what was there."""
    global _override
    previous, _override = _override, load_settings(environ)
    try:
        yield _override
    finally:
        _override = previous


def resolve_environ(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """The mapping a parser reads: the one it was handed, else the current settings' environment."""
    return get_settings().environ if env is None else env


# --- Warehouse schema names (Platform v2, D11) ------------------------------
#
# The schemas the application owns come from the data map (`DATA_MAP_FILE`, or the
# shipped default `docs/data/data-map.json`). `GOLD_SCHEMA`, `OPS_SCHEMA` and
# `SOURCE_SCHEMA` still override a schema name (deprecated: name it in the map).
# They are interpolated into SQL text (a schema cannot be a bound parameter), so
# anything that is not a plain identifier is refused at import rather than
# reaching a statement.

_SHIPPED = data_map.default_map()
DEFAULT_GOLD_SCHEMA = _SHIPPED.gold_schema
DEFAULT_OPS_SCHEMA = _SHIPPED.ops_schema


def schema_name(env_var: str, default: str) -> str:
    """Read a schema name from the environment, refusing a non-identifier."""
    return parse_schema_name(get_settings().environ, env_var, default)


_MAP = data_map.load(get_settings().environ.get("DATA_MAP_FILE"))

#: The read schema: every figure a screen shows.
GOLD_SCHEMA = schema_name("GOLD_SCHEMA", _MAP.gold_schema)

#: Operational and provenance tables: runs, overrides, claims, findings, artifacts.
OPS_SCHEMA = schema_name("OPS_SCHEMA", _MAP.ops_schema)

#: The source schema: the customer's payroll tables in the Fabric Lakehouse
#: (`data/source/`, `DATA_SOURCE=lakehouse`). A customer's own Fabric lakehouse may
#: already use a schema name of its own: set it in the data map's `lakehouse.schema`.
DEFAULT_SOURCE_SCHEMA = _SHIPPED.source_schema

SOURCE_SCHEMA = parse_source_schema(get_settings().environ, _MAP.source_schema)

#: The process's data map (overrides applied) and the logical-name accessors over it:
#: `names.ops.run_manifest`, `names.gold.unit_year_master`.
DATA_MAP = data_map.build(get_settings().environ.get("DATA_MAP_FILE"),
                          {"gold_schema": GOLD_SCHEMA, "ops_schema": OPS_SCHEMA, "source_schema": SOURCE_SCHEMA})
names = data_map.Names(DATA_MAP)
