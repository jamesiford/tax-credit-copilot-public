"""The composition root. Every request-to-handler binding, in one readable place.

Explicit rather than auto-discovered. Decorator registration scattered across
modules is less typing and much harder to answer "what happens when this request
arrives?" from — you have to find the handler before you can read it. Here the
whole dispatch table is one screen.

Import this module once at startup. `get_mediator()` returns the wired instance.
"""
from __future__ import annotations

import os
from typing import Any

from application.deployment import store_choice
from application.commands.assess_client import AssessClientCommand, handle_assess_client
from application.commands.resolve_finding import (
    ReopenFindingCommand,
    ResolveFindingCommand,
    handle_reopen_finding,
    handle_resolve_finding,
)
from application.commands.run_client_calculation import (
    RunClientCalculationCommand,
    handle_run_client_calculation,
)
from application.mediator import Mediator
from application.queries.get_coverage import (
    GetCellHistoryQuery,
    GetClientCoverageQuery,
    GetPortfolioCoverageQuery,
    handle_get_cell_history,
    handle_get_client_coverage,
    handle_get_portfolio_coverage,
)
from application.queries.get_eligibility import (
    GetEligibilityQuery,
    handle_get_eligibility,
)
from application.queries.get_employee_drill import (
    GetEmployeeDrillQuery,
    handle_get_employee_drill,
)
from application.queries.get_in_year_progress import (
    GetInYearProgressQuery,
    handle_get_in_year_progress,
)
from application.queries.get_onezero_matrix import (
    GetOneZeroMatrixQuery,
    handle_get_onezero_matrix,
)
from application.queries.get_client_situation import (
    GetClientSituationQuery,
    handle_get_client_situation,
)
from application.queries.get_proximity import GetProximityQuery, handle_get_proximity
from application.queries.get_unit_trend import GetUnitTrendQuery, handle_get_unit_trend
from application.queries.simulate_portfolio import (
    SimulatePortfolioQuery,
    handle_simulate_portfolio,
)
from application.queries.simulate_unit import SimulateUnitQuery, handle_simulate_unit
from application.queries.simulate_employee import SimulateEmployeeQuery, handle_simulate_employee
from application.queries.rebase_unit import RebaseUnitQuery, handle_rebase_unit
from application.commands.set_base_year import SetBaseYearCommand, handle_set_base_year

_mediator: Mediator | None = None

_claim_repo: Any | None = None
_finding_repo: Any | None = None
_run_manifest_repo: Any | None = None
_gold_writer: Any | None = None
_gold_reader: Any | None = None


def get_claim_repository() -> Any:
    """Composition root for the claim store. [ADR-007]

    One place names the adapter, selected by configuration rather than by code:
    `CLAIM_STORE=warehouse` in a deployed environment, SQLite everywhere else so
    a clone runs offline and CI needs no cloud account.

    The default is deliberately the local one. A misconfigured deployment that
    silently fell back to SQLite would appear to work and lose every filing
    record on the next restart, so choosing the Warehouse is explicit, and a
    deployed process refuses to start on anything else
    (`application.deployment`).

    This lived in `api/claims.py`, which made every command and query handler
    import a router to find its own repository — presentation on the inside of
    application [ADR-003]. Composition belongs in the composition root.
    """
    global _claim_repo
    if _claim_repo is None:
        store = store_choice("CLAIM_STORE")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_claims import WarehouseClaimRepository

            _claim_repo = WarehouseClaimRepository()
        elif store in ("sqlite", "memory"):
            from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

            _claim_repo = SqliteClaimRepository(":memory:" if store == "memory" else None)
        else:
            raise ValueError(
                f"CLAIM_STORE={store!r} is not a known adapter. Use 'warehouse' "
                f"(alias 'fabric'), 'sqlite' or 'memory'. Guessing would put filing "
                f"records somewhere nobody is looking."
            )
    return _claim_repo


def set_claim_repository(repo: Any) -> None:
    """Point the application at another claim adapter. Used by tests."""
    global _claim_repo
    _claim_repo = repo


def get_finding_repository() -> Any:
    """Composition root for the finding store. [ADR-007]

    Selected the same way as the claim store and for the same reason: a finding
    resolution is a human decision that changes a figure on a filed return, and
    a local SQLite file does not survive a redeploy.
    """
    global _finding_repo
    if _finding_repo is None:
        store = store_choice("FINDING_STORE")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_findings import WarehouseFindingRepository

            _finding_repo = WarehouseFindingRepository()
        elif store in ("sqlite", "memory"):
            from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

            _finding_repo = SqliteFindingRepository(":memory:" if store == "memory" else None)
        else:
            raise ValueError(
                f"FINDING_STORE={store!r} is not a known adapter. Use 'warehouse' "
                f"(alias 'fabric'), 'sqlite' or 'memory'. Guessing would put decision "
                f"records somewhere nobody is looking."
            )
    return _finding_repo


def set_finding_repository(repo: Any) -> None:
    """Point the application at another finding adapter. Used by tests."""
    global _finding_repo
    _finding_repo = repo


def get_run_manifest_repository() -> Any:
    """Composition root for run provenance. [ADR-002]

    Selected the same way as the claim and finding stores. The default is the
    in-memory adapter so CI and a fresh clone need no ODBC driver, no Azure
    credential and no Fabric capacity.

    That default is safe only because it is loud: the in-memory adapter reports
    `is_durable = False`, and a deployed environment must set
    `RUN_MANIFEST_STORE=fabric`. A run manifest is the record of which
    calculation produced a figure on a filed return — losing it on a container
    restart means a figure that can no longer be reproduced.
    """
    global _run_manifest_repo
    if _run_manifest_repo is None:
        store = store_choice("RUN_MANIFEST_STORE")
        if store == "warehouse":
            from infrastructure.persistence.fabric_warehouse import (
                FabricRunManifestRepository,
            )

            _run_manifest_repo = FabricRunManifestRepository()
        elif store in ("memory", "sqlite"):
            from infrastructure.persistence.memory_runs import (
                InMemoryRunManifestRepository,
            )

            _run_manifest_repo = InMemoryRunManifestRepository()
        else:
            raise ValueError(
                f"RUN_MANIFEST_STORE={store!r} is not a known adapter. Use "
                f"'warehouse' (alias 'fabric') or 'memory'. Guessing would put "
                f"provenance records somewhere nobody is looking."
            )
    return _run_manifest_repo


_override_repo: Any | None = None


def get_override_repository() -> Any:
    """Composition root for human adjustments (`tcc_ops.manual_override`).

    Follows the run manifest's store unless `OVERRIDE_STORE` says otherwise: an
    override is run provenance — which base a run was told to use — so it lives
    where the run it changes is recorded. Memory is the default only where the
    manifest is memory too, and says so (`is_durable = False`).
    """
    global _override_repo
    if _override_repo is None:
        store = store_choice("OVERRIDE_STORE")
        if store == "warehouse":
            from infrastructure.persistence.fabric_warehouse import FabricManualOverrideRepository

            _override_repo = FabricManualOverrideRepository()
        elif store in ("memory", "sqlite"):
            from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository

            _override_repo = InMemoryManualOverrideRepository()
        else:
            raise ValueError(
                f"OVERRIDE_STORE={store!r} is not a known adapter. Use 'warehouse' "
                f"(alias 'fabric') or 'memory'. Guessing would record a human decision "
                f"somewhere nobody is looking."
            )
    return _override_repo


def set_override_repository(repo: Any) -> None:
    """Point the application at another override adapter. Used by tests."""
    global _override_repo
    _override_repo = repo


def set_run_manifest_repository(repo: Any) -> None:
    """Point the application at another run-manifest adapter. Used by tests."""
    global _run_manifest_repo
    _run_manifest_repo = repo


def get_gold_writer() -> Any:
    """Composition root for the Gold write path. [ADR-002]

    There is no in-memory counterpart on purpose. A stand-in here would accept a
    quarter of a million rows, report success and leave every screen empty —
    which is precisely the failure this write path was built to end. A caller
    without a warehouse gets an error, not a plausible result.
    """
    global _gold_writer
    if _gold_writer is None:
        from infrastructure.persistence.warehouse_gold import GoldWriter

        _gold_writer = GoldWriter()
    return _gold_writer


def set_gold_writer(writer: Any) -> None:
    """Point the application at another Gold writer. Used by tests."""
    global _gold_writer
    _gold_writer = writer


def get_gold_reader() -> Any:
    """Composition root for the Gold read path. [ADR-002]

    Every screen's figures come from here. There is no in-memory counterpart, for
    the same reason the writer has none: a stand-in would answer plausibly and
    from nowhere, and the restart test exists precisely to catch that.
    """
    global _gold_reader
    if _gold_reader is None:
        from infrastructure.persistence.gold_reader import GoldReader

        _gold_reader = GoldReader()
    return _gold_reader


def set_gold_reader(reader: Any) -> None:
    """Point the application at another Gold reader. Used by tests."""
    global _gold_reader
    _gold_reader = reader


# --- Identity [AUTH-3, D24] --------------------------------------------------

_client_authorizer: Any | None = None
_token_validator: Any | None = None


def get_client_authorizer() -> Any:
    """The `ClientAuthorizer` port. v2: every `TCC.User` sees every client (D24)."""
    global _client_authorizer
    if _client_authorizer is None:
        from application.identity import AllClientsAuthorizer

        _client_authorizer = AllClientsAuthorizer()
    return _client_authorizer


def set_client_authorizer(authorizer: Any) -> None:
    """Swap the entitlement policy. Used by tests to prove the deny path."""
    global _client_authorizer
    _client_authorizer = authorizer


def get_token_validator() -> Any:
    """The Entra token validator, built from AUTH_TENANT_ID and API_AUDIENCE."""
    global _token_validator
    if _token_validator is None:
        from application.deployment import auth_tenant_id
        from infrastructure.auth.entra import EntraTokenValidator

        _token_validator = EntraTokenValidator(
            tenant_id=auth_tenant_id(), api_audience=os.getenv("API_AUDIENCE", "").strip()
        )
    return _token_validator


def set_token_validator(validator: Any) -> None:
    global _token_validator
    _token_validator = validator

# --- Artifacts [BLOB-3, BLOB-6] -----------------------------------------------

_artifact_service: Any | None = None


def get_artifact_service() -> Any:
    """Bytes (ARTIFACT_STORE local|blob) + rows (ARTIFACT_REPOSITORY sqlite|warehouse)."""
    global _artifact_service
    if _artifact_service is None:
        from application.artifacts import ArtifactService
        from application.deployment import artifact_repository, artifact_store

        if artifact_store() == "blob":
            from infrastructure.storage.blob_store import BlobArtifactStore

            store: Any = BlobArtifactStore()
        else:
            from infrastructure.storage.local_store import LocalArtifactStore

            store = LocalArtifactStore()
        if artifact_repository() == "warehouse":
            from infrastructure.persistence.warehouse_artifacts import WarehouseArtifactRepository

            repository: Any = WarehouseArtifactRepository()
        else:
            from infrastructure.persistence.sqlite_artifacts import SqliteArtifactRepository

            repository = SqliteArtifactRepository()
        _artifact_service = ArtifactService(
            store, repository, get_client_authorizer(),
            retention_days=int(os.getenv("OUTPUTS_RETENTION_DAYS", "2555")),
        )
    return _artifact_service


def set_artifact_service(service: Any) -> None:
    global _artifact_service
    _artifact_service = service


_claim_package_source: Any | None = None


def get_claim_package_source() -> Any:
    global _claim_package_source
    if _claim_package_source is None:
        from application.claim_package import GoldClaimPackageSource

        _claim_package_source = GoldClaimPackageSource(get_gold_reader(), get_claim_repository())
    return _claim_package_source


def set_claim_package_source(source: Any) -> None:
    global _claim_package_source
    _claim_package_source = source


def build_mediator() -> Mediator:
    """Construct and wire a mediator. Called once; safe to call again in tests."""
    mediator = Mediator()

    # --- Queries: compute and return, change nothing ---
    mediator.register(GetProximityQuery, handle_get_proximity)
    mediator.register(GetEligibilityQuery, handle_get_eligibility)
    mediator.register(GetOneZeroMatrixQuery, handle_get_onezero_matrix)
    mediator.register(GetUnitTrendQuery, handle_get_unit_trend)
    mediator.register(GetEmployeeDrillQuery, handle_get_employee_drill)
    mediator.register(GetClientCoverageQuery, handle_get_client_coverage)
    mediator.register(GetPortfolioCoverageQuery, handle_get_portfolio_coverage)
    mediator.register(GetCellHistoryQuery, handle_get_cell_history)
    mediator.register(SimulatePortfolioQuery, handle_simulate_portfolio)
    mediator.register(SimulateUnitQuery, handle_simulate_unit)
    mediator.register(SimulateEmployeeQuery, handle_simulate_employee)
    mediator.register(RebaseUnitQuery, handle_rebase_unit)
    mediator.register(GetInYearProgressQuery, handle_get_in_year_progress)
    mediator.register(GetClientSituationQuery, handle_get_client_situation)

    # --- Commands: change what the business believes ---
    mediator.register(AssessClientCommand, handle_assess_client)
    mediator.register(ResolveFindingCommand, handle_resolve_finding)
    mediator.register(ReopenFindingCommand, handle_reopen_finding)
    mediator.register(RunClientCalculationCommand, handle_run_client_calculation)
    mediator.register(SetBaseYearCommand, handle_set_base_year)

    return mediator


def get_mediator() -> Mediator:
    """The process-wide mediator, built on first use."""
    global _mediator
    if _mediator is None:
        _mediator = build_mediator()
    return _mediator


def reset_mediator() -> None:
    """Drop the cached instance. For tests that register their own handlers."""
    global _mediator
    _mediator = None
