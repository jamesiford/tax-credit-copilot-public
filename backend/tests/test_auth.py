"""Entra authentication and client authorization at the API edge. [AUTH-3, AUTH-4, AUTH-5, D24, D26]

Tokens are minted here with a throwaway RSA key and served through a fake JWKS
client, so every path — valid, expired, wrong audience, wrong issuer, missing
scope, missing role, no token — is exercised without a tenant.
"""
from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from application import wiring
from application.identity import ANONYMOUS, AllClientsAuthorizer, AllowListAuthorizer, Principal
from infrastructure.auth.entra import (
    AuthenticationFailed,
    AuthorizationFailed,
    EntraTokenValidator,
    audiences,
    issuer_for,
)

TENANT = "00000000-0000-0000-0000-0000000000aa"
API_CLIENT_ID = "11111111-2222-3333-4444-555555555555"
AUDIENCE = f"api://{API_CLIENT_ID}"
OID = "oid-analyst-1"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    """PyJWKClient's interface, serving one public key."""

    def __init__(self, key=_KEY):
        self.public = key.public_key()
        self.calls = 0

    def get_signing_key_from_jwt(self, token):
        self.calls += 1
        jwt.get_unverified_header(token)  # malformed tokens fail here, as they would for real
        return self.public


def mint(*, key=_KEY, aud=API_CLIENT_ID, iss=None, scp="user_impersonation", roles=("TCC.User",),
         exp_in=3600, upn="analyst@example.com", **extra) -> str:
    now = int(time.time())
    claims = {
        "aud": aud, "iss": iss or issuer_for(TENANT), "iat": now, "nbf": now, "exp": now + exp_in,
        "oid": OID, "tid": TENANT, "preferred_username": upn, "name": "Ana Lyst",
        "scp": scp, "roles": list(roles), **extra,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def _validator() -> EntraTokenValidator:
    return EntraTokenValidator(tenant_id=TENANT, api_audience=AUDIENCE, jwks_client=FakeJwks())


# ----------------------------------------------------------- the validator


def test_a_valid_token_yields_the_principal():
    principal = _validator().validate(mint())
    assert principal.authenticated and principal.oid == OID
    assert principal.upn == "analyst@example.com" and principal.actor == "analyst@example.com"
    assert "TCC.User" in principal.roles and "user_impersonation" in principal.scopes


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "not-a-jwt",
        mint(exp_in=-3600),                                   # expired
        mint(aud="api://some-other-api"),                     # wrong audience
        mint(iss="https://login.microsoftonline.com/other-tenant/v2.0"),  # wrong issuer
        mint(iss=f"https://sts.windows.net/{TENANT}/"),       # v1 issuer
        mint(key=_OTHER_KEY),                                 # forged signature
    ],
    ids=["none", "empty", "garbage", "expired", "audience", "issuer", "v1-issuer", "signature"],
)
def test_anything_short_of_proof_is_a_401(token):
    with pytest.raises(AuthenticationFailed):
        _validator().validate(token)


@pytest.mark.parametrize(
    "token, why",
    [(mint(scp="openid profile"), "user_impersonation"), (mint(roles=()), "TCC.User"), (mint(roles=("Reader",)), "TCC.User")],
    ids=["no-scope", "no-roles", "wrong-role"],
)
def test_proven_identity_without_scope_or_role_is_a_403(token, why):
    with pytest.raises(AuthorizationFailed, match=why):
        _validator().validate(token)


def test_both_audience_forms_are_accepted():
    assert audiences("api://abc") == ["api://abc", "abc"]
    _validator().validate(mint(aud=AUDIENCE))
    _validator().validate(mint(aud=API_CLIENT_ID))


def test_keys_are_fetched_through_the_injected_client():
    validator = _validator()
    validator.validate(mint())
    assert validator.jwks_client.calls == 1


# --------------------------------------------------------- the API edge


@pytest.fixture
def entra(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("API_AUDIENCE", AUDIENCE)
    wiring.set_token_validator(_validator())
    yield
    wiring.set_token_validator(None)
    wiring.set_client_authorizer(None)


@pytest.fixture
def api():
    import main

    return TestClient(main.app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_needs_no_token(entra, api):
    assert api.get("/api/health").status_code == 200


def test_no_token_is_401_with_a_bearer_challenge(entra, api):
    response = api.get("/api/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("token", [mint(exp_in=-3600), mint(aud="api://other")], ids=["expired", "audience"])
def test_an_invalid_token_is_401(entra, api, token):
    assert api.get("/api/me", headers=_auth(token)).status_code == 401


@pytest.mark.parametrize("token", [mint(scp="openid"), mint(roles=())], ids=["scope", "role"])
def test_a_token_without_scope_or_role_is_403(entra, api, token):
    assert api.get("/api/me", headers=_auth(token)).status_code == 403


def test_me_returns_the_callers_identity(entra, api):
    body = api.get("/api/me", headers=_auth(mint())).json()
    assert body == {
        "auth_mode": "entra", "authenticated": True, "upn": "analyst@example.com",
        "oid": OID, "name": "Ana Lyst", "roles": ["TCC.User"],
    }


def test_an_unauthorized_client_is_403_in_path_query_and_body(entra, api):
    """A fake authorizer proves the deny path (D24)."""
    wiring.set_client_authorizer(AllowListAuthorizer({OID: {1001}}))
    token = _auth(mint())
    assert api.get("/api/claims/coverage/2001", headers=token).status_code == 403
    assert api.get("/api/proximity/2023", params={"account_id": 2001}, headers=token).status_code == 403
    denied = api.post(
        "/api/findings/x/resolve", headers=token,
        json={"client_id": 2001, "tax_year": 2023, "resolution": "accept"},
    )
    assert denied.status_code == 403 and "2001" in denied.json()["detail"]
    assert api.get("/api/claims/coverage/1001", headers=token).status_code != 403


def test_writes_are_attributed_to_the_token_not_the_body(entra, api, tmp_path):
    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

    repo = SqliteFindingRepository(tmp_path / "f.db")
    wiring.set_finding_repository(repo)
    try:
        response = api.post(
            "/api/findings/t2:E1:3/resolve", headers=_auth(mint()),
            json={"client_id": 1001, "tax_year": 2023, "resolution": "flag", "decided_by": "someone-else@example.com"},
        )
        assert response.status_code == 200, response.text
        [live] = repo.live(1001)
        assert live.decided_by == "analyst@example.com"
    finally:
        wiring.set_finding_repository(None)
        repo.close()


# --------------------------------------------------------- AUTH_MODE=none


def test_none_mode_is_anonymous_and_keeps_the_request_attribution(monkeypatch, api, tmp_path):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    body = api.get("/api/me").json()
    assert body["auth_mode"] == "none" and body["authenticated"] is False and body["upn"] is None

    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

    repo = SqliteFindingRepository(tmp_path / "f.db")
    wiring.set_finding_repository(repo)
    try:
        api.post("/api/findings/t2:E1:3/resolve", json={"client_id": 1001, "tax_year": 2023, "resolution": "flag"})
        api.post("/api/findings/t2:E2:3/resolve", json={
            "client_id": 1001, "tax_year": 2023, "resolution": "flag", "decided_by": "local.dev@example.com"})
        decided = sorted(r.decided_by for r in repo.live(1001))
        assert decided == ["anonymous", "local.dev@example.com"], "never a name the server invented"
    finally:
        wiring.set_finding_repository(None)
        repo.close()


def test_the_default_authorizer_allows_every_client():
    assert AllClientsAuthorizer().is_authorized(ANONYMOUS, 1001)
    assert AllClientsAuthorizer().is_authorized(Principal(oid="x", authenticated=True), 2004)


# ------------------------------------------------------- startup refusal


@pytest.mark.parametrize(
    "env, refused",
    [
        ({"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "customer", "AUTH_MODE": "none"}, True),
        ({"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "customer"}, True),   # none is the default
        ({"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", "AUTH_MODE": "none"}, False),
        ({"ENVIRONMENT": "local", "DATA_CLASSIFICATION": "customer", "AUTH_MODE": "none"}, False),
        ({"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "customer", "AUTH_MODE": "entra",
          "AUTH_TENANT_ID": TENANT, "API_AUDIENCE": AUDIENCE}, False),
    ],
)
def test_auth_none_is_refused_for_customer_data_when_deployed(env, refused):
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    stores = {"CLAIM_STORE": "warehouse", "FINDING_STORE": "warehouse", "RUN_MANIFEST_STORE": "warehouse",
              "ARTIFACT_STORE": "blob", "ARTIFACT_REPOSITORY": "warehouse"}
    if refused:
        with pytest.raises(DeploymentConfigurationError, match="AUTH_MODE=none"):
            check_deployment_configuration({**stores, **env})
    else:
        check_deployment_configuration({**stores, **env})


@pytest.mark.parametrize("missing", ["AUTH_TENANT_ID", "API_AUDIENCE"])
def test_entra_mode_needs_its_tenant_and_audience(missing):
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    env = {"AUTH_MODE": "entra", "AUTH_TENANT_ID": TENANT, "API_AUDIENCE": AUDIENCE}
    env.pop(missing)
    with pytest.raises(DeploymentConfigurationError, match=missing):
        check_deployment_configuration(env)


def test_an_unknown_auth_mode_is_refused():
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    with pytest.raises(DeploymentConfigurationError, match="AUTH_MODE"):
        check_deployment_configuration({"AUTH_MODE": "basic"})
