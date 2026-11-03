"""Composition: settings in, a ready `TurnPipeline` out. [CH-08]

The one place that knows how the pieces fit, so the hosting shell (`main.py`) stays a few lines
and the tests build the same pipeline around fakes. Every collaborator can be handed in.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.gateway_client import GatewayClient, managed_identity_token
from app.core.models import ModelChain, build_providers
from app.core.planner import Planner
from app.core.settings import OrchestratorSettings, load_settings
from app.core.state import StateStore
from app.core.turn import TurnPipeline
from application.ai.safety.injection import PromptInjectionGuard

log = logging.getLogger("tcc.orchestrator")


@dataclass
class Orchestrator:
    """The composed process: settings, the pipeline and the pieces `/whoami` reports on."""

    settings: OrchestratorSettings
    pipeline: TurnPipeline
    chain: ModelChain
    gateway: GatewayClient


def effective_environment(env: Mapping[str, str]) -> dict[str, str]:
    """The environment with the platform's model deployment name used as `FOUNDRY_MODEL` when none is set."""
    merged = dict(env)
    if not merged.get("FOUNDRY_MODEL") and merged.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"):
        merged["FOUNDRY_MODEL"] = merged["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    return merged


def build_orchestrator(
    env: Mapping[str, str] | None = None, *, gateway: GatewayClient | None = None, chain: ModelChain | None = None,
) -> Orchestrator:
    """Build from the environment. Raises `OrchestratorConfigError` naming every problem."""
    settings = load_settings(effective_environment(os.environ if env is None else env))
    if settings.debug_whoami:
        log.warning(
            "CHANNEL_DEBUG_WHOAMI is ON: /whoami, /netcheck and /modelprobe answer anyone who can message this agent. "
            "Demo and identity spikes only; switch it off afterwards (docs/m365-channel/DEMO-CLEANUP.md).",
        )
    gateway = gateway or GatewayClient(
        settings.gateway_url, managed_identity_token(settings.gateway_scope), timeout_seconds=settings.request_timeout_seconds,
    )
    safety = settings.ai.safety
    chain = chain or ModelChain(
        build_providers(settings), egress_policy=settings.ai.egress_policy,
        timeout_seconds=settings.ai.resilience.total_deadline_s,
        injection=PromptInjectionGuard() if safety.injection_guard else None,
    )
    planner = Planner(chain, allowed_hosts=safety.output_allowed_hosts)
    pipeline = TurnPipeline(settings, gateway, planner, StateStore(settings.state_ttl_seconds))
    return Orchestrator(settings, pipeline, chain, gateway)
