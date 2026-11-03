"""`scripts/assign-channel-roles.ps1 -GrantUserReadBasic`: one Graph role, to one identity, idempotently. [CH-15a]

The script runs for real under pwsh against the fake `az` the publish tests use (`tests/publish_shim.py`), so what
is asserted is the requests it makes: the role it assigns, to whom, and that an existing assignment, a switch left
off and `-WhatIf` all make no write. Every identifier is an obvious placeholder.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests import publish_shim as shim

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "assign-channel-roles.ps1"

pytestmark = pytest.mark.skipif(shim.PWSH is None, reason="PowerShell 7 (pwsh) is not installed")

API_APP, GATEWAY_APP = "aaaaaaaa-0000-4000-8000-00000000000a", "bbbbbbbb-0000-4000-8000-00000000000b"
GATEWAY_IDENTITY = "cccccccc-0000-4000-8000-00000000000c"
API_SP, GATEWAY_SP, GRAPH_SP = "sp-api", "sp-gateway", "sp-graph"
ROLE_AGENT, ROLE_BASIC, ROLE_GROUPS = "role-tcc-agent", "role-user-read-basic", "role-group-member-read"


def principal(identifier: str, name: str, roles: dict[str, str]) -> dict:
    return {"id": identifier, "displayName": name,
            "appRoles": [{"id": rid, "value": value, "allowedMemberTypes": ["Application"]} for value, rid in roles.items()]}


def scenario(*, assigned: tuple[tuple[str, str], ...] = (), deny: bool = False) -> dict:
    """Service principals come back in the order the script asks: API, gateway, Graph."""
    post = {"stderr": "ERROR: Authorization_RequestDenied (403)", "exit": 1} if deny else {"stdout": {}}
    existing = [{"principalId": GATEWAY_IDENTITY, "appRoleId": role} for _, role in assigned]
    return {"tenant": shim.TENANT, "subscription": shim.SUBSCRIPTION, "rest": [
        {"match": r"^GET .*/servicePrincipals$", "responses": [
            {"stdout": {"value": [principal(API_SP, "API", {"TCC.Agent": ROLE_AGENT})]}},
            {"stdout": {"value": [principal(GATEWAY_SP, "Gateway", {"Channel.Invoke": "role-invoke"})]}},
            {"stdout": {"value": [principal(GRAPH_SP, "Microsoft Graph", {"User.ReadBasic.All": ROLE_BASIC, "GroupMember.Read.All": ROLE_GROUPS})]}},
        ]},
        {"match": r"^GET .*/appRoleAssignedTo$", "responses": [{"stdout": {"value": existing}}]},
        {"match": r"^POST .*/appRoleAssignedTo$", "responses": [post]},
    ]}


def run(tmp_path, *extra, plan=None, identity=True):
    fake = shim.Fake(tmp_path, plan or scenario())
    arguments = [shim.PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                 "-ApiApplicationId", API_APP, "-GatewayApplicationId", GATEWAY_APP,
                 *(["-GatewayIdentityPrincipalId", GATEWAY_IDENTITY] if identity else []), *extra]
    done = subprocess.run(arguments, capture_output=True, text=True, env=fake.environment(), timeout=180)
    return fake, done


def calls(fake) -> list[dict]:
    return [json.loads(line) for line in fake.log.read_text(encoding="utf-8").splitlines()] if fake.log.exists() else []


def posts(fake) -> list[dict]:
    return [c for c in calls(fake) if "POST" in c["args"] and "rest" in c["args"]]


def assigned_roles(fake) -> list[tuple[str, str, str]]:
    return [(p["body"]["appRoleId"], p["body"]["principalId"], p["body"]["resourceId"]) for p in posts(fake)]


def test_the_switch_assigns_only_user_read_basic_to_the_gateway_identity_on_graph(tmp_path):
    fake, done = run(tmp_path, "-GrantUserReadBasic")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (ROLE_BASIC, GATEWAY_IDENTITY, GRAPH_SP) in assigned_roles(fake)
    assert ROLE_GROUPS not in {role for role, _, _ in assigned_roles(fake)}
    assert "assigned: User.ReadBasic.All" in done.stdout


def test_without_the_switch_the_graph_role_is_never_assigned(tmp_path):
    fake, done = run(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert ROLE_BASIC not in {role for role, _, _ in assigned_roles(fake)}


def test_an_existing_assignment_is_reported_and_left_alone(tmp_path):
    fake, done = run(tmp_path, "-GrantUserReadBasic", plan=scenario(assigned=(("TCC.Agent", ROLE_AGENT), ("User.ReadBasic.All", ROLE_BASIC))))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "already assigned: User.ReadBasic.All" in done.stdout
    assert posts(fake) == []


def test_a_second_run_is_a_no_op_for_the_role(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first, _ = run(tmp_path / "one", "-GrantUserReadBasic")
    assert ROLE_BASIC in {role for role, _, _ in assigned_roles(first)}
    both = scenario(assigned=(("TCC.Agent", ROLE_AGENT), ("User.ReadBasic.All", ROLE_BASIC)))
    second, done = run(tmp_path / "two", "-GrantUserReadBasic", plan=both)
    assert assigned_roles(second) == [] and "already assigned" in done.stdout


def test_a_caller_who_may_not_grant_gets_the_exact_command_and_exit_code_two(tmp_path):
    fake, done = run(tmp_path, "-GrantUserReadBasic", plan=scenario(deny=True))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "ADMIN ACTIONS" in done.stdout and "DENIED: User.ReadBasic.All" in done.stdout
    assert f"/servicePrincipals/{GRAPH_SP}/appRoleAssignedTo" in done.stdout and ROLE_BASIC in done.stdout


def test_whatif_assigns_nothing(tmp_path):
    fake, done = run(tmp_path, "-GrantUserReadBasic", "-WhatIf")
    assert done.returncode == 0, done.stdout + done.stderr
    assert posts(fake) == []


def test_the_role_goes_to_the_gateway_identity_so_the_switch_needs_one(tmp_path):
    fake, done = run(tmp_path, "-GrantUserReadBasic", identity=False)
    assert done.returncode == 1 and "-GatewayIdentityPrincipalId" in (done.stdout + done.stderr)
    assert posts(fake) == []
