"""The only live dispatcher: runtime-only identities, fixed SQL and bounded HTTPS GETs."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import asyncio
import io
import json
import os
from pathlib import Path
import struct

from admission import HERE, capacity_admission
from catalogue import CASES, Refused
from sampling import Marker, paired, unmeasured
from transport import Target, read

REQUIRED = ("SHADOW_PYTHON_ORIGIN", "SHADOW_DOTNET_ORIGIN", "SHADOW_PYTHON_BEARER",
            "SHADOW_DOTNET_BEARER", "SHADOW_SOURCE_ODBC", "SHADOW_SOURCE_TOKEN",
            "SHADOW_ACCOUNT", "SHADOW_YEAR")
PROOFS = ("SHADOW_TRUSTED_INGRESS", "SHADOW_EMPLOYER_BINDING",
          "SHADOW_MATCHED_CALLER_RIGHTS", "SHADOW_MATCHED_SOURCE_AND_GOLD")
CATALOGUE = json.loads((HERE / "sql-catalogue.json").read_text(encoding="utf-8"))


def connection_options(value: str) -> dict:
    allowed = {"driver", "server", "database", "encrypt", "trustservercertificate", "applicationintent"}
    options = {}
    for pair in value.split(";"):
        if not pair.strip():
            continue
        key, separator, item = pair.partition("=")
        key = key.strip().lower()
        if not separator or key not in allowed or key in options:
            raise Refused("sql-transport")
        options[key] = item.strip()
    if (options.get("encrypt", "").lower() != "yes"
            or options.get("trustservercertificate", "").lower() != "no"
            or options.get("applicationintent", "").lower() != "readonly"
            or options.get("driver") != "{ODBC Driver 18 for SQL Server}"
            or not options.get("server") or not options.get("database")):
        raise Refused("sql-transport")
    return options


def prerequisites(environment: dict) -> list[str]:
    missing = []
    if any(not environment.get(key) for key in REQUIRED):
        missing.append("runtime-endpoints-identities-or-readonly-credentials-missing")
    if any(environment.get(key) != "reviewed" for key in PROOFS):
        missing.append("ingress-employer-rights-or-destination-proof-missing")
    return missing


@contextmanager
def source_reader(environment: dict):
    """ApplicationIntent is not a grant proof: null or effective protected writes refuse dispatch."""
    import pyodbc

    connection_string = environment["SHADOW_SOURCE_ODBC"]
    connection_options(connection_string)
    token = environment["SHADOW_SOURCE_TOKEN"].encode("utf-16-le")
    connection = pyodbc.connect(connection_string, attrs_before={1256: struct.pack("<I", len(token)) + token, 104: 0},
                                timeout=10, autocommit=True)
    try:
        connection.timeout = 5
        cursor = connection.cursor()
        permissions = tuple(cursor.execute(CATALOGUE["permissions"]).fetchone())
        if (len(permissions) != 17 or permissions[1] != 1
                or any(value != 0 for i, value in enumerate(permissions) if i != 1)):
            raise Refused("read-only-grants-unproved")
        if cursor.execute(CATALOGUE["writable_objects"]).fetchone()[0] != 0:
            raise Refused("read-only-grants-unproved")

        def fingerprint():
            sql = CATALOGUE["fingerprint"].replace("@account", "?")
            row = cursor.execute(sql, int(environment["SHADOW_ACCOUNT"])).fetchone()
            return Marker(int(row[0]), row[1])
        yield fingerprint
    finally:
        connection.close()


def fetch(host: str, case: str, environment: dict) -> dict:
    import httpx

    async def once():
        target = Target(environment[f"SHADOW_{host.upper()}_ORIGIN"], environment[f"SHADOW_{host.upper()}_BEARER"])
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False,
                                     limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)) as client:
            return await read(client, target, case, int(environment["SHADOW_ACCOUNT"]), int(environment["SHADOW_YEAR"]))
    return asyncio.run(once())


def run(check: Path, environment: dict | None = None) -> dict:
    environment = dict(os.environ if environment is None else environment)
    admission = capacity_admission(check)
    reasons = prerequisites(environment)
    if admission.get("capacity") != "active":
        reasons.insert(0, "current-capacity-not-admitted")
    result = {"mode": "live", "admission": admission, "groups": unmeasured(reasons),
              "scratch": {"used": False, "created": 0, "cleanup": "not-needed-no-live-scratch"},
              "protected_writes_dispatched": 0}
    if reasons:
        return result
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                source_reader(environment) as fingerprint:
            for case in ("health", "eligibility", "drafts"):
                result["groups"][CASES[case].group] = paired(
                    case, lambda host: fetch(host, case, environment), fingerprint)
        # Audit-writing and unavailable capabilities never inherit eligibility from unrelated reads.
        for case in ("gateway", "ai", "sealed", "rules"):
            result["groups"][CASES[case].group] = unmeasured(["side-effect-or-coverage-excluded"])[CASES[case].group]
    except Exception:  # noqa: BLE001 - no endpoint/driver text; retain failed live admission as unmeasured
        for group in result["groups"].values():
            if not group["attempted"]:
                group["unmeasured_reasons"] = ["read-only-grants-or-runtime-dependency-unproved"]
        result["verdict"] = "incomplete-observation"
    return result
