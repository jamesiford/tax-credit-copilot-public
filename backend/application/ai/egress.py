"""What may leave the platform, and the one thing that never does. [AI-03]

Two layers, deliberately different:

* The INVARIANT is not configurable: an employee identifier or an opaque record
  token never enters a prompt, for any provider, under any policy. It is already a
  repository rule ("employee IDs … must not enter … a Foundry prompt"); this makes
  it a check that fails closed rather than a convention. Record tokens are 24
  lowercase hex characters; a 64-hex trail hash is a different thing and passes.
* The POLICY (`AI_EGRESS_POLICY`) is a lever for providers outside Microsoft's
  boundary (`gateway`, `foundry_connection`): `allow_all` (the default — the owner
  has confirmed no payroll PII needs redaction), `aggregates_only` (refuse a prompt
  carrying row-grain keys) or `block` (nothing leaves).

A refused prompt is `EgressRefused`, a bad-request kind of failure. It is decided
per provider, so a prompt a gateway may not receive can still go to Foundry; the
identifier invariant refuses every provider, and the caller shows the engine's own
blocks instead.
"""
from __future__ import annotations

import json
import re

from domain.ai import EgressDecision, ModelRole

#: Providers whose model runs outside Microsoft's boundary, behind a gateway.
EXTERNAL_PROVIDERS = frozenset({"gateway", "foundry_connection"})

_RECORD_TOKEN = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{24}(?![0-9a-fA-F])")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_IDENTIFIER_KEY = re.compile(r'"(?:employee_ids?|employee_id_hash|record_tokens?|ssn)"\s*:', re.IGNORECASE)
_ROW_GRAIN_KEY = re.compile(r"employee|record_token|ssn|worksite|unit_id|evidence|person", re.IGNORECASE)


def identifier_findings(prompt: str) -> list[str]:
    """Why this prompt carries an identifier, or []. Never echoes the match."""
    found = []
    if _RECORD_TOKEN.search(prompt):
        found.append("an employee record token")
    if _SSN.search(prompt):
        found.append("a social-security-number-shaped value")
    if _IDENTIFIER_KEY.search(prompt):
        found.append("an employee identifier field")
    return found


def _row_grain_keys(node: object) -> bool:
    if isinstance(node, dict):
        return any(_ROW_GRAIN_KEY.search(str(k)) or _row_grain_keys(v) for k, v in node.items())
    if isinstance(node, list):
        return any(_row_grain_keys(v) for v in node)
    return False


def _json_part(prompt: str) -> object | None:
    marker = prompt.rfind("JSON:")
    try:
        return json.loads(prompt[marker + 5:]) if marker >= 0 else None
    except ValueError:
        return None


class _Base:
    name = "base"

    def prepare(self, prompt: str, *, role: ModelRole, provider: str) -> EgressDecision:
        found = identifier_findings(prompt)
        if found:
            return EgressDecision(False, prompt, self.name, f"the prompt carries {', '.join(found)}")
        return self._policy(prompt, provider)

    def _policy(self, prompt: str, provider: str) -> EgressDecision:
        return EgressDecision(True, prompt, self.name)


class AllowAll(_Base):
    """Send what the caller built; identifiers are still refused (the invariant is policy-independent)."""

    name = "allow_all"


class AggregatesOnly(_Base):
    """Refuse a prompt to an external provider unless it is the aggregate brief the engine built."""

    name = "aggregates_only"

    def _policy(self, prompt: str, provider: str) -> EgressDecision:
        if provider not in EXTERNAL_PROVIDERS:
            return EgressDecision(True, prompt, self.name)
        brief = _json_part(prompt)
        if brief is None or _row_grain_keys(brief):
            return EgressDecision(False, prompt, self.name, "only aggregate briefs may leave for an external provider")
        return EgressDecision(True, prompt, self.name)


class BlockExternal(_Base):
    """Send nothing to an external provider at all."""

    name = "block"

    def _policy(self, prompt: str, provider: str) -> EgressDecision:
        if provider in EXTERNAL_PROVIDERS:
            return EgressDecision(False, prompt, self.name, "nothing may leave for an external provider")
        return EgressDecision(True, prompt, self.name)


def build_egress_policy(name: str):
    """The policy `AI_EGRESS_POLICY` names."""
    return {"allow_all": AllowAll, "aggregates_only": AggregatesOnly, "block": BlockExternal}[name]()
