"""One shared Azure credential, local runs without the managed-identity probe. [03.4]"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import override_settings
from infrastructure import azure_credential as ac

BACKEND = Path(__file__).resolve().parent.parent


def _kinds(credential) -> list[str]:
    return [type(c).__name__ for c in credential.credentials]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("AZURE_TOKEN_CREDENTIALS", raising=False)
    ac.reset_for_tests()
    yield
    ac.reset_for_tests()


def test_a_local_credential_leaves_out_the_managed_identity_probe():
    assert "ManagedIdentityCredential" not in _kinds(ac.build_credential(deployed=False))


def test_a_deployed_credential_keeps_the_managed_identity():
    assert "ManagedIdentityCredential" in _kinds(ac.build_credential(deployed=True, managed_identity_client_id="abc"))


def test_an_operator_choice_of_credential_is_applied_by_the_sdk_not_overridden(monkeypatch):
    monkeypatch.setenv("AZURE_TOKEN_CREDENTIALS", "managedidentitycredential")
    only_mi = ac.build_credential(deployed=False, token_credentials="managedidentitycredential")
    assert _kinds(only_mi) == ["ManagedIdentityCredential"], "no exclusion flag was passed over the operator's value"


def test_settings_decide_local_or_deployed():
    with override_settings({"ENVIRONMENT": "local"}):
        assert "ManagedIdentityCredential" not in _kinds(ac.new_credential())
    with override_settings({"ENVIRONMENT": "azure", "AZURE_CLIENT_ID": "abc"}):
        assert "ManagedIdentityCredential" in _kinds(ac.new_credential())
    with override_settings({}):
        assert "ManagedIdentityCredential" not in _kinds(ac.new_credential()), "unset ENVIRONMENT is local"


def test_the_shared_credential_is_built_once_and_a_new_one_is_not_the_shared_one():
    first = ac.shared_credential()
    assert ac.shared_credential() is first
    assert ac.new_credential() is not first


class _Credential:
    def __init__(self):
        self.calls = 0
        self.expires_on = 10**10

    def get_token(self, scope):
        self.calls += 1
        return SimpleNamespace(token=f"t{self.calls}:{scope}", expires_on=self.expires_on)


def test_a_token_is_reused_until_shortly_before_it_expires(monkeypatch):
    fake = _Credential()
    monkeypatch.setattr(ac, "_shared", fake)
    assert ac.cached_token("scope-a") == ac.cached_token("scope-a") == "t1:scope-a"
    assert ac.cached_token("scope-b") == "t2:scope-b", "tokens are per scope"
    fake.expires_on = 0
    ac.reset_for_tests()
    monkeypatch.setattr(ac, "_shared", fake)
    assert ac.cached_token("scope-a") != ac.cached_token("scope-a"), "an expired token is refetched every time"


def test_the_token_is_never_logged(monkeypatch, caplog):
    monkeypatch.setattr(ac, "_shared", _Credential())
    with caplog.at_level("DEBUG"):
        token = ac.cached_token("scope-a")
    assert token not in caplog.text


#: The only direct constructions left, each with the reason it is not the shared factory. A new one fails the test below.
REMAINING_DIRECT_SITES = {
    "backend/infrastructure/ai/auth/entra_token.py": (
        "the default branch of a module the orchestrator vendors and cannot import `backend` for; the backend passes "
        "the shared credential in (`bootstrap/ai_wiring.py`), so this branch runs only inside the orchestrator"
    ),
    "channel_orchestrator/app/core/gateway_client.py": "the hosted orchestrator is a separate deployable that cannot import `backend`; built once at wiring",
    "channel_orchestrator/app/core/maf_foundry_client.py": "same deployable; built once per scope behind an `lru_cache`, which a test pins as 'once per process'",
    "channel_orchestrator/app/core/modelprobe.py": "same deployable; a debug-only diagnostic that deliberately mirrors the platform sample's own call",
}


def test_the_remaining_direct_credential_sites_are_exactly_the_documented_ones():
    """Everything that talks to Azure shares one credential, except these. Adding another needs a reason here."""
    repo = BACKEND.parent
    found = set()
    for base in ("backend", "channel_orchestrator/app", "scripts"):
        for path in (repo / base).rglob("*.py"):
            relative = path.relative_to(repo).as_posix()
            if "/tests/" in relative or "/vendor/" in relative or relative.endswith("infrastructure/azure_credential.py"):
                continue
            if re.search(r"\bDefaultAzureCredential\(", path.read_text(encoding="utf-8")):
                found.add(relative)
    assert found == set(REMAINING_DIRECT_SITES), (
        f"direct DefaultAzureCredential constructions changed: {sorted(found ^ set(REMAINING_DIRECT_SITES))}"
    )
    assert all(reason.strip() for reason in REMAINING_DIRECT_SITES.values())


# The rule that keeps it one place: a second `DefaultAzureCredential(` is how the probe came back.
_ALLOWED = {
    "infrastructure/azure_credential.py": "the factory",
}


def test_default_azure_credential_is_constructed_only_by_the_factory():
    found = []
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", "channel_orchestrator/", ".venv/")) or "__pycache__" in relative:
            continue
        if relative in _ALLOWED or relative == "infrastructure/ai/auth/entra_token.py":
            continue
        if re.search(r"\bDefaultAzureCredential\(", path.read_text(encoding="utf-8")):
            found.append(relative)
    assert not found, f"build credentials through infrastructure.azure_credential: {found}"
