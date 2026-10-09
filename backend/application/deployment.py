"""What a deployed environment must be configured as, checked before it serves. [DATA-5, AUTH-5, D26]

Two settings decide it, and both are explicit rather than inferred:

- `ENVIRONMENT` — `local` (the default: a clone, a test run, CI) or anything
  else, which means deployed. A deployed process holds decisions that land on a
  filed return, so every store it writes must be durable.
- `DATA_CLASSIFICATION` — `synthetic` or `customer`. Required once
  `ENVIRONMENT != local`. Never guessed from a hostname or a data source,
  because guessing wrong in one direction exposes payroll and in the other
  blocks a demo.

A misconfiguration raises at startup. Falling back would look like it worked:
SQLite on an App Service writes to a filesystem the platform may discard, and an
in-memory store forgets every decision on the next restart.
"""
from __future__ import annotations

import os
from typing import Mapping

LOCAL = "local"
CLASSIFICATIONS = ("synthetic", "customer")

#: Store names that persist beyond the process.
DURABLE_STORES = frozenset({"warehouse"})
#: Accepted spellings, normalised. `fabric` is the v1 name for the Warehouse.
_ALIASES = {"fabric": "warehouse"}

#: The four operational stores and their LOCAL defaults.
STORE_DEFAULTS = {
    "CLAIM_STORE": "sqlite",
    "FINDING_STORE": "sqlite",
    "RUN_MANIFEST_STORE": "memory",
}


class DeploymentConfigurationError(RuntimeError):
    """The process is configured in a way a deployed environment must refuse."""


def _get(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def environment(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return (_get(env, "ENVIRONMENT") or LOCAL).lower()


def is_deployed(env: Mapping[str, str] | None = None) -> bool:
    return environment(env) != LOCAL


def data_classification(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    value = _get(env, "DATA_CLASSIFICATION").lower()
    return value or None


AUTH_MODES = ("none", "entra")


def auth_mode(env: Mapping[str, str] | None = None) -> str:
    """`none` (default) or `entra`. Unknown values are reported by the startup check."""
    env = os.environ if env is None else env
    return (_get(env, "AUTH_MODE") or "none").lower()


def auth_tenant_id(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return _get(env, "AUTH_TENANT_ID") or _get(env, "AZURE_TENANT_ID")


def normalise_store(value: str) -> str:
    value = value.strip().lower()
    return _ALIASES.get(value, value)


def store_choice(name: str, env: Mapping[str, str] | None = None) -> str:
    """The configured adapter for one store, aliases resolved.

    `OVERRIDE_STORE` follows `RUN_MANIFEST_STORE` unless set: an override is run
    provenance and lives where the run it changes is recorded.
    """
    env = os.environ if env is None else env
    if name == "OVERRIDE_STORE":
        default = store_choice("RUN_MANIFEST_STORE", env)
    else:
        default = STORE_DEFAULTS[name]
    return normalise_store(_get(env, name) or default)


def store_names() -> tuple[str, ...]:
    return (*STORE_DEFAULTS, "OVERRIDE_STORE")


#: Artifact bytes and artifact rows (BLOB-6): local defaults, durable choices.
ARTIFACT_STORES = ("local", "blob")
ARTIFACT_REPOSITORIES = ("sqlite", "warehouse")


def artifact_store(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return (_get(env, "ARTIFACT_STORE") or "local").lower()


def artifact_repository(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return normalise_store(_get(env, "ARTIFACT_REPOSITORY") or "sqlite")


def check_deployment_configuration(env: Mapping[str, str] | None = None) -> dict[str, str | None]:
    """Raise `DeploymentConfigurationError` if this process must not start.

    Returns the resolved settings, for logging and `/api/health`.
    """
    env = os.environ if env is None else env
    problems: list[str] = []

    classification = data_classification(env)
    if classification is not None and classification not in CLASSIFICATIONS:
        problems.append(
            f"DATA_CLASSIFICATION={classification!r} is not one of {', '.join(CLASSIFICATIONS)}"
        )

    mode = auth_mode(env)
    if mode not in AUTH_MODES:
        problems.append(f"AUTH_MODE={mode!r} is not one of {', '.join(AUTH_MODES)}")
    elif mode == "entra":
        if not auth_tenant_id(env):
            problems.append("AUTH_MODE=entra needs AUTH_TENANT_ID (or AZURE_TENANT_ID)")
        if not _get(env, "API_AUDIENCE"):
            problems.append("AUTH_MODE=entra needs API_AUDIENCE (the API app registration)")

    stores = {name: store_choice(name, env) for name in store_names()}
    deployed = is_deployed(env)
    if deployed and mode == "none" and classification == "customer":
        problems.append(
            "AUTH_MODE=none is refused with DATA_CLASSIFICATION=customer outside a local "
            "environment (D26): customer payroll is never served without authentication"
        )
    if deployed:
        if classification is None:
            problems.append(
                "DATA_CLASSIFICATION is required when ENVIRONMENT is not 'local' "
                "(synthetic or customer; it is never inferred)"
            )
        for name, store in stores.items():
            if store not in DURABLE_STORES:
                problems.append(
                    f"{name}={store!r} is not durable; a deployed environment must use 'warehouse'"
                )

    bytes_store, rows_store = artifact_store(env), artifact_repository(env)
    if bytes_store not in ARTIFACT_STORES:
        problems.append(f"ARTIFACT_STORE={bytes_store!r} is not one of {', '.join(ARTIFACT_STORES)}")
    if rows_store not in ARTIFACT_REPOSITORIES:
        problems.append(f"ARTIFACT_REPOSITORY={rows_store!r} is not one of {', '.join(ARTIFACT_REPOSITORIES)}")
    if deployed and bytes_store != "blob":
        problems.append(f"ARTIFACT_STORE={bytes_store!r} is not durable; a deployed environment must use 'blob'")
    if deployed and rows_store != "warehouse":
        problems.append(
            f"ARTIFACT_REPOSITORY={rows_store!r} is not durable; a deployed environment must use 'warehouse'"
        )

    if problems:
        raise DeploymentConfigurationError(
            f"refusing to start (ENVIRONMENT={environment(env)!r}):\n  - " + "\n  - ".join(problems)
        )
    return {"environment": environment(env), "data_classification": classification, "auth_mode": mode,
            "ARTIFACT_STORE": bytes_store, "ARTIFACT_REPOSITORY": rows_store, **stores}
