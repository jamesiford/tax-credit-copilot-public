"""What the application layer asks of the composition root, and nothing it could import.

A handler is a plain function registered with the mediator, so it finds its
collaborators by asking for them. It used to ask `application.wiring`, which named
every adapter under `infrastructure/`: the layer that is supposed to implement the
application's ports was being imported BY it. The rule is now that `application`
imports nothing from `infrastructure` or `bootstrap`; the composition root
(`bootstrap/`) registers a provider for each name below at import, and the getters
here call it.

A provider is a callable, not an instance, so it is resolved on every call. That
keeps the root's `set_*` and a test's `monkeypatch.setattr(wiring, "get_x", ...)`
effective for the handlers that ask, which a value copied at start-up would not be.

Routers ask here too: nothing under `api/` imports `infrastructure` or `bootstrap`
(RM-18). A service locator is a deliberate, interim shape: constructor injection is
the destination, and until a handler is built around its collaborators this is the
smallest change that points the dependency the right way.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.gold_read_port import GoldReadPort
    from application.mediator import Mediator

_providers: dict[str, Callable[[], Any]] = {}


class ServiceNotBound(RuntimeError):
    """Nothing in the composition root provides this service.

    Its own type so a process that never imported `bootstrap` fails with the
    sentence that names the cause rather than an `AttributeError` somewhere deep.
    """


def provide(name: str, provider: Callable[[], Any]) -> None:
    """Register (or replace) the provider for `name`. Called by the composition root only."""
    _providers[name] = provider


def resolve(name: str) -> Any:
    """The service `name`, from whatever the composition root bound for it."""
    try:
        provider = _providers[name]
    except KeyError:
        raise ServiceNotBound(
            f"no provider is bound for {name!r}. The composition root (`bootstrap`) must be imported "
            f"by the entry point before the application is used."
        ) from None
    return provider()


def get_mediator() -> Mediator:
    return resolve("mediator")


def get_claim_repository() -> Any:
    return resolve("claim_repository")


def get_finding_repository() -> Any:
    return resolve("finding_repository")


def get_run_manifest_repository() -> Any:
    return resolve("run_manifest_repository")


def get_override_repository() -> Any:
    return resolve("override_repository")


def get_gold_reader() -> GoldReadPort:
    return resolve("gold_reader")


def get_gold_writer() -> Any:
    return resolve("gold_writer")


def get_artifact_service() -> Any:
    return resolve("artifact_service")


def get_claim_package_source() -> Any:
    return resolve("claim_package_source")


def get_narration_service() -> Any:
    return resolve("narration_service")


def get_confirmation_repository() -> Any:
    return resolve("confirmation_repository")


def get_confirmation_service() -> Any:
    return resolve("confirmation_service")


def get_channel_auditor() -> Any:
    return resolve("channel_auditor")


def get_channel_audit_repository() -> Any:
    return resolve("channel_audit_repository")


def get_writer_entitlement() -> Any:
    return resolve("writer_entitlement")


def get_data_query_service() -> Any:
    return resolve("data_query_service")


def get_token_validator() -> Any:
    return resolve("token_validator")


def get_client_authorizer() -> Any:
    return resolve("client_authorizer")


def get_agent_action_recorder() -> Any:
    return resolve("agent_action_recorder")


def get_output_policy() -> Any:
    return resolve("output_policy")


def get_ai_telemetry() -> Any:
    return resolve("ai_telemetry")
