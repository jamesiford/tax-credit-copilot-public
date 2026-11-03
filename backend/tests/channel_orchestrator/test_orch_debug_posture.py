"""The demo's diagnostic switch is off by default, shouts when on, and has a cleanup page. [CH-15e]

`CHANNEL_DEBUG_WHOAMI` turns on commands (`/whoami`, `/netcheck`, `/modelprobe`) and a gateway tool
(`channel_ping`) that exist to settle identity and network questions during a demo. Left on, they
answer anyone who can reach the agent. Everything that holds a default for it must say `false`, a
process that starts with it on must say so in its log, and the person closing the demo needs the
exact commands, in order.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.settings import load_settings as load_orchestrator_settings
from app.wiring import build_orchestrator
from orch_harness import ENV, FakeGateway

ROOT = Path(__file__).resolve().parents[3]
WARNING_TEXT = "CHANNEL_DEBUG_WHOAMI is ON"


def _orchestrator(env, caplog):
    from app.core.models import ModelChain

    settings = load_orchestrator_settings({**ENV, **env})
    chain = ModelChain([], egress_policy=settings.ai.egress_policy, timeout_seconds=1.0)
    with caplog.at_level(logging.INFO, logger="tcc.orchestrator"):
        return build_orchestrator({**ENV, **env}, gateway=FakeGateway().client(), chain=chain)


def test_the_orchestrator_default_is_off_and_says_nothing(caplog):
    assert load_orchestrator_settings(ENV).debug_whoami is False
    _orchestrator({}, caplog)
    assert WARNING_TEXT not in caplog.text


def test_the_orchestrator_warns_at_startup_when_the_switch_is_on(caplog):
    orch = _orchestrator({"CHANNEL_DEBUG_WHOAMI": "true"}, caplog)
    assert orch.settings.debug_whoami is True
    [record] = [r for r in caplog.records if WARNING_TEXT in r.getMessage()]
    assert record.levelno == logging.WARNING and "DEMO-CLEANUP.md" in record.getMessage()


def test_every_default_for_the_switch_is_false():
    azure = (ROOT / "channel_orchestrator" / "azure.yaml").read_text(encoding="utf-8")
    assert "CHANNEL_DEBUG_WHOAMI: ${CHANNEL_DEBUG_WHOAMI=false}" in azure
    for path in ("infra/variables.tf", "infra/modules/channel/main.tf"):
        text = (ROOT / path).read_text(encoding="utf-8")
        block = re.search(r'variable "(?:channel_)?debug_whoami" \{(.*?)\n\}', text, re.S).group(1)
        assert re.search(r"default\s*=\s*false", block), path


def test_the_cleanup_page_exists_and_names_the_switch_and_its_command():
    page = (ROOT / "docs" / "m365-channel" / "DEMO-CLEANUP.md").read_text(encoding="utf-8")
    assert "azd env set CHANNEL_DEBUG_WHOAMI false" in page
    assert "channel_debug_whoami = false" in page
    for topic in ("foundry_allow_any_ip", "channel_allowed_caller_app_ids", "enable_mock_ai_gateway", "TCC_CHANNEL_WRITER_SOURCE allowlist"):
        assert topic in page, topic
