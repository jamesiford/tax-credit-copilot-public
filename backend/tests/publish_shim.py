"""A programmable fake `az` for the publish script's tests, and the placeholder values it answers with. [CH-09]

`install(tmp_path, scenario)` puts an `az` first on PATH that logs every call (its arguments and, for
`az rest --body @file`, the JSON that file held) and answers from a scenario: tenant and subscription ids,
the provider state, the agent's definition, and scripted responses per `METHOD url-regex` (consumed in order,
the last one repeating). `az rest --output-file` writes a real package zip. Nothing reaches Azure, and every
identifier here is an obvious placeholder, so what the tests (and the saved WhatIf transcript) print is safe to
commit.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import zipfile  # noqa: F401 - used by the shim source below
from pathlib import Path

TENANT = "11111111-1111-4111-8111-111111111111"
SUBSCRIPTION = "22222222-2222-4222-8222-222222222222"
CLIENT_ID = "33333333-3333-4333-8333-333333333333"
ENDPOINT = "https://account-example.services.ai.azure.com/api/projects/project-example"
AGENT = "tcc-channel-orchestrator"
BOT = "bot-tcc-channel-example"
GROUP = "rg-example"

SHIM = r'''
import json, os, re, sys, zipfile
args = sys.argv[1:]
scenario = json.load(open(os.environ["FAKE_AZ_SCENARIO"]))

def option(name):
    return args[args.index(name) + 1] if name in args else None

entry = {"args": args}
if option("--body"):
    entry["body"] = json.load(open(option("--body").lstrip("@"), encoding="utf-8-sig"))
with open(os.environ["FAKE_AZ_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(entry) + "\n")

def finish(response):
    if response.get("stderr"):
        sys.stderr.write(response["stderr"])
    out = response.get("stdout")
    if out is not None:
        print(out if isinstance(out, str) else json.dumps(out))
    sys.exit(response.get("exit", 0))

if args[:2] == ["account", "show"]:
    print(scenario["tenant"] if option("--query") == "tenantId" else scenario["subscription"])
elif args[:2] == ["provider", "show"]:
    print(scenario.get("provider", "Registered"))
elif args[:1] == ["rest"]:
    key = option("--method") + " " + option("--url").split("?")[0]
    for rule in scenario["rest"]:
        if re.search(rule["match"], key):
            queue = rule["responses"]
            response = queue.pop(0) if len(queue) > 1 else queue[0]
            json.dump(scenario, open(os.environ["FAKE_AZ_SCENARIO"], "w"))
            if response.get("zip") and option("--output-file"):
                with zipfile.ZipFile(option("--output-file"), "w") as z:
                    z.writestr("manifest.json", json.dumps(response["zip"]))
                    z.writestr("color.png", b"png")
            finish(response)
    sys.stderr.write("fake az: no scripted response for " + key)
    sys.exit(9)
else:
    sys.stderr.write("fake az: unexpected command " + " ".join(args))
    sys.exit(9)
'''

MANIFEST = {"id": "44444444-4444-4444-8444-444444444444", "version": "1.0.0", "name": {"short": "Example agent"},
            "developer": {"name": "Example developer"}, "bots": [{"botId": CLIENT_ID}]}


def default_agent() -> dict:
    return {
        "name": AGENT, "instance_identity": {"principal_id": "55555555-5555-4555-8555-555555555555", "client_id": CLIENT_ID},
        "agent_endpoint": {
            "protocol_configuration": {"responses": {}, "invocations": {"keep": "me"}},
            "authorization_schemes": [{"type": "AzureRbac"}, {"type": "BotServiceTenant"}],
            "version_selector": {"version_selection_rules": [{"type": "FixedRatio", "agent_version": "7", "traffic_percentage": 100}]},
        },
    }


def default_scenario() -> dict:
    return {
        "tenant": TENANT, "subscription": SUBSCRIPTION, "provider": "Registered",
        "rest": [
            {"match": r"^get .*/agents/[^/]+$", "responses": [{"stdout": default_agent()}]},
            {"match": r"^put .*/botServices/[^/]+$", "responses": [{"stdout": {}}]},
            {"match": r"^put .*/channels/MsTeamsChannel$", "responses": [{"stdout": {}}]},
            {"match": r"^patch .*/agents/[^/]+$", "responses": [{"stdout": {}}]},
            {"match": r"^post .*/microsoft365/publish$", "responses": [{"stdout": {"titleId": "T_example-title-id"}}]},
            {"match": r"^post .*/microsoft365/zip$", "responses": [{"zip": MANIFEST}]},
        ],
    }


def route(scenario: dict, match_fragment: str, *responses: dict) -> None:
    """Replace the scripted responses of the rule whose pattern contains `match_fragment`."""
    for rule in scenario["rest"]:
        if match_fragment in rule["match"]:
            rule["responses"] = list(responses)
            return
    raise KeyError(match_fragment)


class Fake:
    """An installed fake `az`: where it lives, what it logged, and how to run a script with it first on PATH."""

    def __init__(self, directory: Path, scenario: dict) -> None:
        self.dir, self.log, self.scenario_file = directory / "bin", directory / "az.log", directory / "scenario.json"
        self.dir.mkdir()
        self.scenario_file.write_text(json.dumps(scenario), encoding="utf-8")
        shim = directory / "fake_az.py"
        shim.write_text(textwrap.dedent(SHIM), encoding="utf-8")
        if os.name == "nt":
            (self.dir / "az.cmd").write_text(f'@echo off\r\n"{sys.executable}" "{shim}" %*\r\nexit /b %ERRORLEVEL%\r\n', encoding="ascii")
        else:
            script = self.dir / "az"
            script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{shim}" "$@"\n', encoding="ascii")
            script.chmod(0o755)

    def environment(self) -> dict[str, str]:
        return {**os.environ, "PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}",
                "FAKE_AZ_SCENARIO": str(self.scenario_file), "FAKE_AZ_LOG": str(self.log)}

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def rest(self, method: str) -> list[dict]:
        """Every `az rest` call with that method, as `{url, body, headers, resource, args}`."""
        found = []
        for call in self.calls():
            args = call["args"]
            if args[:1] == ["rest"] and args[args.index("--method") + 1] == method:
                found.append({"url": args[args.index("--url") + 1], "body": call.get("body"), "args": args,
                              "resource": args[args.index("--resource") + 1] if "--resource" in args else None,
                              "headers": args[args.index("--headers") + 1] if "--headers" in args else None})
        return found


def install(directory: Path, scenario: dict | None = None) -> Fake:
    return Fake(directory, scenario or default_scenario())


def required_arguments() -> list[str]:
    return ["-ProjectEndpoint", ENDPOINT, "-AgentName", AGENT, "-ResourceGroup", GROUP, "-BotName", BOT,
            "-DisplayName", "Tax Credit Copilot", "-ShortDescription", "Questions about job-creation tax credits.",
            "-FullDescription", "Answers from the platform's own calculations, with the figures it computed."]


PWSH = shutil.which("pwsh")
