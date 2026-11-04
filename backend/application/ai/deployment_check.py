"""What the AI settings must satisfy before a process may start. [AI-03]

The same refuse-to-start pattern as `application/deployment.py`: a configuration
that would fail at the first question, or send prompts somewhere unsafe, stops the
process instead. Called from `check_deployment_configuration`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.ai.settings import load_ai_settings


def ai_problems(env: Mapping[str, Any], deployed: bool) -> list[str]:
    """Each reason the AI configuration cannot be used, as a sentence."""
    try:
        settings = load_ai_settings(env)
    except ValueError as exc:
        return [str(exc)]
    problems: list[str] = []
    gateway = settings.gateway
    if gateway is not None and deployed:
        if not gateway.tls_verify:
            problems.append(
                "AI_GATEWAY_TLS_VERIFY=false is refused when ENVIRONMENT is not 'local': "
                "prompts must not travel to a gateway whose certificate is not checked"
            )
        if gateway.auth == "none":
            problems.append("AI_GATEWAY_AUTH=none is refused when ENVIRONMENT is not 'local'")
    return problems
