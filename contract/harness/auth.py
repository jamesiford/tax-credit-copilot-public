"""Sign-in for the contract run: AUTH_MODE=entra with a key pair generated at run time and an in-memory JWKS.

Nothing here is a secret and nothing is written to a file: the RSA keys exist only in the server process, tokens are minted on request
(`POST /__contract__/mint`) and the recordings hold the placeholder `Bearer {{token.<name>}}`, never a token. An implementation under
test offers the same hook, minting with its own test key.
"""
from __future__ import annotations

import os
import time
from typing import Any

TENANT = "00000000-0000-0000-0000-0000000000aa"
API_CLIENT_ID = "11111111-2222-3333-4444-555555555555"
AUDIENCE = f"api://{API_CLIENT_ID}"

#: Fixed object ids so authorisation decisions are reproducible.
OID_READER = "00000000-0000-0000-0000-0000000000a1"
OID_WRITER = "00000000-0000-0000-0000-0000000000a2"
OID_RESTRICTED = "00000000-0000-0000-0000-0000000000a3"
OID_GATEWAY = "00000000-0000-0000-0000-0000000000b1"

_keys: dict[str, Any] = {}
_installed = False


def _key(name: str) -> Any:
    from cryptography.hazmat.primitives.asymmetric import rsa

    if name not in _keys:
        _keys[name] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _keys[name]


class FakeJwks:
    """PyJWKClient's interface, serving the main key's public half."""

    def get_signing_key_from_jwt(self, token: str) -> Any:
        import jwt

        jwt.get_unverified_header(token)
        return _key("main").public_key()


def install(rate_limit_per_minute: int = 3) -> None:
    """Switch the running app to Entra sign-in. Call after the world is built and before the first request."""
    global _installed
    from application import request_limits
    from application.identity import AllowListAuthorizer
    from application.rate_limit import RateLimiter
    from bootstrap import channel_wiring, wiring
    from domain.channel import WriterGrant
    from infrastructure.auth.entra import EntraTokenValidator

    os.environ.update({
        "AUTH_MODE": "entra", "AUTH_TENANT_ID": TENANT, "API_AUDIENCE": AUDIENCE, "CHANNEL_ENFORCE_WRITER_FOR_USERS": "true",
        "RATE_LIMIT_PER_MINUTE": str(rate_limit_per_minute), "ENVIRONMENT": "local",
    })
    from bootstrap import auth_wiring

    auth_wiring.set_token_validator(EntraTokenValidator(tenant_id=TENANT, api_audience=AUDIENCE, jwks_client=FakeJwks()))
    auth_wiring.set_client_authorizer(AllowListAuthorizer({OID_READER: {1001, 2001, 2002, 2003, 2004}, OID_WRITER: {1001, 2001, 2002, 2003, 2004},
                                                           OID_RESTRICTED: {999}, OID_GATEWAY: {1001, 2001, 2002, 2003, 2004}}))
    channel_wiring.get_writer_repository().grant(WriterGrant(user_oid=OID_WRITER, added_by="contract", display_name="Writer"))
    # A frozen clock for the per-caller limiter: Retry-After is then a function of the request count, not of elapsed real time.
    request_limits.reset()
    request_limits._limiters[rate_limit_per_minute] = RateLimiter(rate_limit_per_minute, clock=lambda: 0.0)
    wiring.reset_mediator()
    _installed = True


def mint(spec: dict[str, Any]) -> str:
    import jwt

    from infrastructure.auth.entra import issuer_for

    kind = spec.get("kind", "user")
    now = int(time.time())
    oid = spec.get("oid", OID_READER if kind == "user" else OID_GATEWAY)
    claims: dict[str, Any] = {"aud": spec.get("aud", API_CLIENT_ID), "iss": spec.get("iss", issuer_for(TENANT)), "iat": now, "nbf": now + int(spec.get("nbf_in", 0)),
                              "exp": now + int(spec.get("exp_in", 3600)), "oid": oid, "tid": spec.get("tid", TENANT)}
    if kind == "user":
        claims.update({"preferred_username": spec.get("upn", "analyst@example.test"), "name": spec.get("name", "Ana Lyst"),
                       "scp": spec.get("scp", "user_impersonation"), "roles": spec.get("roles", ["TCC.User"])})
    else:
        claims.update({"idtyp": "app", "sub": oid, "roles": spec.get("roles", ["TCC.Agent"])})
    claims.update(spec.get("claims") or {})
    for name in spec.get("drop") or []:
        claims.pop(name, None)
    return jwt.encode(claims, _key(spec.get("key", "main")), algorithm="RS256", headers={"kid": "contract-key"})
