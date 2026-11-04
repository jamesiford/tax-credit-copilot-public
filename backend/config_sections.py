"""The typed sections of `config.Settings`, each parsed from a plain mapping. [RM-20, D-142]

Nothing here touches the process: every parser takes the mapping it is given, so a
test builds any section from a dict and `config.py` stays the one module that reads
the environment. Defaults are the values the readers used before they were gathered
here, and a value that used to raise still raises (a bad number is a typo that
decides something, not a case to guess).

Variables that are parsed elsewhere, on purpose, are not repeated here: the AI,
knowledge and safety settings (`application/ai/settings.py`, `knowledge_settings.py`),
which the orchestrator vendors and so cannot import this module; the sign-in and
deployment-posture checks (`application/auth_policy.py`, `deployment.py`); the
gateway (`channel/config.py`); and the data-query limits (`bootstrap/data_wiring.py`).
Those take a mapping too, and the composition root hands them `Settings.environ`.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 90
DEFAULT_STRANDED_RUN_MINUTES = 60
DEFAULT_KEEPALIVE_SECONDS = 30
DEFAULT_RETENTION_DAYS = 2555
DEFAULT_EMPLOYEES_TABLE = "dbo/employees"
DEFAULT_FLEX_ACCOUNT_ID = 1001
DEFAULT_WEBIQ_BASE_URL = "https://api.microsoft.ai/v3"

#: Schema names are interpolated into SQL text (a schema cannot be a bound parameter),
#: so anything that is not a plain identifier is refused rather than reaching a statement.
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def parse_schema_name(environ: Mapping[str, str], env_var: str, default: str) -> str:
    """A schema name from the mapping, refusing a non-identifier."""
    value = (environ.get(env_var) or default).strip()
    if not IDENTIFIER.match(value):
        raise ValueError(
            f"{env_var}={value!r} is not a plain SQL identifier; schema names are "
            f"interpolated into statements and must match {IDENTIFIER.pattern}"
        )
    return value


@dataclass(frozen=True)
class RuntimeSettings:
    """What a process stamps on its runs and how it starts."""

    git_commit: str | None
    log_level: str
    warm_on_start: bool
    keepalive_seconds: int


@dataclass(frozen=True)
class ObservabilitySettings:
    """Telemetry and the flags `/api/health` reports. A value is a setting's presence, never a secret."""

    appinsights_connection_string: str | None
    azure_client_id: str | None
    foundry_project_endpoint: str | None


@dataclass(frozen=True)
class DataSourceSettings:
    """Where payroll comes from. `explicit_data_source` is the raw choice, `None` when it was not made."""

    data_source: str
    explicit_data_source: str | None
    fabric_workspace: str | None
    fabric_lakehouse: str | None
    fabric_employees_table: str
    flex_account_id: int
    reference_access_output_path: str | None


@dataclass(frozen=True)
class WarehouseSettings:
    """The Fabric Warehouse and the lakehouse SQL endpoint. Empty string means unset."""

    server: str
    database: str
    odbc_driver: str
    connect_timeout: int
    lakehouse_sql_server: str
    lakehouse_sql_database: str
    stranded_run_minutes: int


@dataclass(frozen=True)
class StoresSettings:
    """Local store locations and the artifact retention period."""

    operational_db: str | None
    artifact_local_root: str | None
    artifact_blob_account_url: str
    outputs_retention_days: int
    claim_store: str

    def operational_db_or(self, default: str | Path) -> str | Path:
        """The configured SQLite path, else the adapter's own default. Set-but-empty stays empty, as it did."""
        return default if self.operational_db is None else self.operational_db


@dataclass(frozen=True)
class WebIqSettings:
    """The rules-ingestion web search. `base_url` is `None` until set, so a module can keep its own default."""

    base_url: str | None
    api_key: str | None
    bearer_token: str | None


def _keepalive(environ: Mapping[str, str]) -> int:
    """How often to touch the pool. An unparseable value is the default: this is tuning, not policy."""
    try:
        return max(5, int(environ.get("TCC_KEEPALIVE_SECONDS", str(DEFAULT_KEEPALIVE_SECONDS))))
    except ValueError:
        return DEFAULT_KEEPALIVE_SECONDS


def parse_runtime(environ: Mapping[str, str]) -> RuntimeSettings:
    warm = environ.get("TCC_WARM_ON_START", "1").strip().lower() not in ("0", "false", "no")
    return RuntimeSettings(
        git_commit=environ.get("GIT_COMMIT"), log_level=environ.get("LOG_LEVEL", "INFO"),
        warm_on_start=warm, keepalive_seconds=_keepalive(environ),
    )


def parse_observability(environ: Mapping[str, str]) -> ObservabilitySettings:
    return ObservabilitySettings(
        appinsights_connection_string=environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
        azure_client_id=environ.get("AZURE_CLIENT_ID") or None,
        foundry_project_endpoint=environ.get("FOUNDRY_PROJECT_ENDPOINT"),
    )


def parse_data_source(environ: Mapping[str, str]) -> DataSourceSettings:
    return DataSourceSettings(
        data_source=environ.get("DATA_SOURCE", "lakehouse").strip().lower(),
        explicit_data_source=environ.get("DATA_SOURCE") or None,
        fabric_workspace=environ.get("FABRIC_WORKSPACE"),
        fabric_lakehouse=environ.get("FABRIC_LAKEHOUSE"),
        fabric_employees_table=environ.get("FABRIC_EMPLOYEES_TABLE", DEFAULT_EMPLOYEES_TABLE),
        flex_account_id=int(environ.get("FLEX_ACCOUNT_ID", str(DEFAULT_FLEX_ACCOUNT_ID))),
        reference_access_output_path=environ.get("REFERENCE_ACCESS_OUTPUT_PATH") or None,
    )


def parse_warehouse(environ: Mapping[str, str]) -> WarehouseSettings:
    return WarehouseSettings(
        server=environ.get("WAREHOUSE_SERVER") or "",
        database=environ.get("WAREHOUSE_DATABASE") or "",
        odbc_driver=environ.get("WAREHOUSE_ODBC_DRIVER") or DEFAULT_ODBC_DRIVER,
        connect_timeout=int(environ.get("WAREHOUSE_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT_SECONDS)),
        lakehouse_sql_server=environ.get("LAKEHOUSE_SQL_SERVER") or "",
        lakehouse_sql_database=environ.get("LAKEHOUSE_SQL_DATABASE") or "",
        stranded_run_minutes=int(environ.get("TCC_STRANDED_RUN_MINUTES", DEFAULT_STRANDED_RUN_MINUTES)),
    )


def parse_stores(environ: Mapping[str, str]) -> StoresSettings:
    return StoresSettings(
        operational_db=environ.get("OPERATIONAL_DB"),
        artifact_local_root=environ.get("ARTIFACT_LOCAL_ROOT") or None,
        artifact_blob_account_url=environ.get("ARTIFACT_BLOB_ACCOUNT_URL") or "",
        outputs_retention_days=int(environ.get("OUTPUTS_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)),
        claim_store=environ.get("CLAIM_STORE", "sqlite"),
    )


def parse_webiq(environ: Mapping[str, str]) -> WebIqSettings:
    return WebIqSettings(
        base_url=environ.get("WEBIQ_BASE_URL"),
        api_key=environ.get("WEBIQ_API_KEY") or None,
        bearer_token=environ.get("WEBIQ_BEARER_TOKEN") or None,
    )
