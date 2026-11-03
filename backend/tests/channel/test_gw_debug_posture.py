"""The gateway says so at startup when its diagnostic tool is on. [CH-15e]"""
from __future__ import annotations

import logging

from gateway_harness import build_gateway

WARNING_TEXT = "CHANNEL_DEBUG_WHOAMI is ON"


def test_a_gateway_with_the_diagnostic_off_logs_no_warning(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="tcc.channel"):
        build_gateway(tmp_path)
    assert WARNING_TEXT not in caplog.text


def test_a_gateway_with_the_diagnostic_on_warns_and_points_at_the_cleanup_page(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="tcc.channel"):
        build_gateway(tmp_path, debug_whoami=True)
    [record] = [r for r in caplog.records if WARNING_TEXT in r.getMessage()]
    assert record.levelno == logging.WARNING and "DEMO-CLEANUP.md" in record.getMessage()
