"""Fixtures for the gateway tests. [CH-06]"""
from __future__ import annotations

import pytest

from gateway_harness import FakeApi, Gateway, build_gateway


@pytest.fixture
def fake_api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def gateway(tmp_path, fake_api) -> Gateway:
    return build_gateway(tmp_path, api=fake_api)
