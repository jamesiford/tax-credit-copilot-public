"""The channel's stores, composed: audit, writers, confirmations, entitlement. [CH-03, CH-06, ADR-008]

Split out of `application.wiring`, which re-exports every name here, for one reason:
the channel gateway needs exactly these and nothing else. `wiring` imports every
query and command in the product, so a gateway that composed itself through it
would load the whole engine to write an audit row. This module imports no handler,
no query and no framework; the persistence adapters are imported inside the
getters, only when that store is chosen.

`CHANNEL_STORE` selects the adapter (`warehouse` | `sqlite` | `memory`). A deployed
process refuses anything but `warehouse` (`application.deployment`).
"""
from __future__ import annotations

from typing import Any

from application.deployment import store_choice

_channel_audit_repo: Any | None = None
_agent_action_repo: Any | None = None
_writer_repo: Any | None = None
_confirmation_repo: Any | None = None
_writer_entitlement: Any | None = None
_display_name_resolver: Any | None = None


def _channel_store(name: str) -> str:
    store = store_choice("CHANNEL_STORE")
    if store not in ("warehouse", "sqlite", "memory"):
        raise ValueError(
            f"CHANNEL_STORE={store!r} is not a known adapter. Use 'warehouse' (alias "
            f"'fabric'), 'sqlite' or 'memory'. Guessing would put the {name} somewhere nobody is looking."
        )
    return store


def get_channel_audit_repository() -> Any:
    """The per-user channel audit trail. `CHANNEL_STORE` selects the adapter."""
    global _channel_audit_repo
    if _channel_audit_repo is None:
        store = _channel_store("channel audit trail")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_channel import WarehouseChannelAuditRepository

            _channel_audit_repo = WarehouseChannelAuditRepository()
        else:
            from infrastructure.persistence.sqlite_channel import SqliteChannelAuditRepository

            _channel_audit_repo = SqliteChannelAuditRepository(":memory:" if store == "memory" else None)
    return _channel_audit_repo


def set_channel_audit_repository(repo: Any) -> None:
    global _channel_audit_repo
    _channel_audit_repo = repo


def get_agent_action_audit_repository() -> Any:
    """`tcc_ops.agent_action_audit`: one row per narrator-agent call."""
    global _agent_action_repo
    if _agent_action_repo is None:
        store = _channel_store("agent action trail")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_channel import WarehouseAgentActionAuditRepository

            _agent_action_repo = WarehouseAgentActionAuditRepository()
        else:
            from infrastructure.persistence.sqlite_channel import SqliteAgentActionAuditRepository

            _agent_action_repo = SqliteAgentActionAuditRepository(":memory:" if store == "memory" else None)
    return _agent_action_repo


def set_agent_action_audit_repository(repo: Any) -> None:
    global _agent_action_repo
    _agent_action_repo = repo


def get_writer_repository() -> Any:
    """The writer allow-list (`tcc_ops.channel_user`)."""
    global _writer_repo
    if _writer_repo is None:
        store = _channel_store("writer allow-list")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_channel_state import WarehouseWriterRepository

            _writer_repo = WarehouseWriterRepository()
        else:
            from infrastructure.persistence.sqlite_channel_state import SqliteWriterRepository

            _writer_repo = SqliteWriterRepository(":memory:" if store == "memory" else None)
    return _writer_repo


def set_writer_repository(repo: Any) -> None:
    global _writer_repo
    _writer_repo = repo


def get_writer_entitlement() -> Any:
    """The `WriterEntitlement` for `CHANNEL_WRITER_SOURCE`."""
    global _writer_entitlement
    if _writer_entitlement is None:
        from application.deployment import writer_group_id, writer_source
        from infrastructure.auth.writers import EitherEntitlement, EntraGroupEntitlement

        source = writer_source()
        allow = get_writer_repository()
        if source == "allowlist":
            _writer_entitlement = allow
        else:
            group = EntraGroupEntitlement(writer_group_id())
            _writer_entitlement = group if source == "entra_group" else EitherEntitlement((allow, group))
    return _writer_entitlement


def set_writer_entitlement(entitlement: Any) -> None:
    """Swap the entitlement source. Used by tests."""
    global _writer_entitlement
    _writer_entitlement = entitlement


def get_display_name_resolver() -> Any:
    """The Graph display-name lookup [CH-15a]. The gateway asks for it only when CHANNEL_RESOLVE_DISPLAY_NAMES is on."""
    global _display_name_resolver
    if _display_name_resolver is None:
        from infrastructure.auth.graph_people import GraphDisplayNameResolver

        _display_name_resolver = GraphDisplayNameResolver()
    return _display_name_resolver


def set_display_name_resolver(resolver: Any) -> None:
    """Swap the display-name lookup. Used by tests."""
    global _display_name_resolver
    _display_name_resolver = resolver


def get_confirmation_repository() -> Any:
    """Prepare/commit tokens, by hash (`tcc_ops.channel_confirmation`)."""
    global _confirmation_repo
    if _confirmation_repo is None:
        store = _channel_store("confirmation tokens")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_channel_state import WarehouseConfirmationRepository

            _confirmation_repo = WarehouseConfirmationRepository()
        else:
            from infrastructure.persistence.sqlite_channel_state import SqliteConfirmationRepository

            _confirmation_repo = SqliteConfirmationRepository(":memory:" if store == "memory" else None)
    return _confirmation_repo


def set_confirmation_repository(repo: Any) -> None:
    global _confirmation_repo
    _confirmation_repo = repo


def get_channel_auditor() -> Any:
    from application.channel_audit import ChannelAuditor

    return ChannelAuditor(get_channel_audit_repository())


def get_agent_action_recorder() -> Any:
    from application.agent_audit import AgentActionRecorder

    return AgentActionRecorder(get_agent_action_audit_repository())
