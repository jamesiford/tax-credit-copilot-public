"""External replay must establish the same scenario world as a spawned oracle."""
from __future__ import annotations

import json
import urllib.request

from contract.harness.auth import AUDIENCE, TENANT


def prepare_external(base_url: str, reset_url: str, scenario: dict) -> None:
    """Keep profile/auth setup ahead of token minting, not in product routes."""
    _post(reset_url, {"profile": scenario["profile"]})
    auth = scenario.get("auth")
    values = {
        "AUTH_MODE": "entra" if auth else "none",
        "CHANNEL_ENFORCE_WRITER_FOR_USERS": "true" if auth else "false",
        "RATE_LIMIT_PER_MINUTE": str(
            auth.get("rate_limit_per_minute", 3) if isinstance(auth, dict) else 3
        ) if auth else "60",
    }
    if auth:
        values.update({"AUTH_TENANT_ID": TENANT, "API_AUDIENCE": AUDIENCE})
    _post(base_url.rstrip("/") + "/__contract__/env", {"set": values})


def _post(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        url, json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        if response.status != 200:
            raise RuntimeError("External scenario setup failed before replay.")
