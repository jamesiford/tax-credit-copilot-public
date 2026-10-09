"""Focused compatibility tests for Foundry agent definitions."""
from __future__ import annotations

from agents.factory import _supports_temperature


def test_gpt5_models_omit_temperature():
    assert _supports_temperature("gpt-5.4-mini") is False
    assert _supports_temperature(" GPT-5 ") is False


def test_legacy_models_keep_temperature():
    assert _supports_temperature("gpt-4.1") is True
    assert _supports_temperature("gpt-4o") is True