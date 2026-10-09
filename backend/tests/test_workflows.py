"""The deploy workflow is dispatch-only, uses OIDC, and stores no secret. [HOST-6, D23]"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _on_block(text: str) -> str:
    match = re.search(r"^on:\n((?:[ \t].*\n|\n)*)", text, re.M)
    assert match, "no top-level on: block"
    return match.group(1)


def test_deploy_runs_only_on_manual_dispatch():
    on = _on_block((WORKFLOWS / "deploy.yml").read_text(encoding="utf-8"))
    assert "workflow_dispatch:" in on
    for trigger in ("push:", "pull_request", "schedule:", "workflow_run:"):
        assert trigger not in on, f"deploy.yml must not trigger on {trigger} (D23)"


def test_deploy_uses_oidc_and_no_stored_secret():
    text = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    assert "id-token: write" in text and "azure/login@" in text
    assert "secrets." not in text, "Azure identifiers are variables; no secret is stored (HOST-6)"


def test_deploy_requires_remote_state_and_asserts_its_target():
    text = (WORKFLOWS / "deploy.yml").read_text(encoding="utf-8")
    for name in ("TF_BACKEND_RESOURCE_GROUP", "TF_BACKEND_STORAGE_ACCOUNT", "TF_BACKEND_CONTAINER"):
        assert name in text
    assert "EXPECTED_SUBSCRIPTION" in text and "az account show --query id" in text
    assert text.index("name: Assert the target subscription") < text.index("name: Terraform apply")


def test_ci_runs_terraform_gitleaks_and_actionlint():
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    for needle in ("terraform fmt -check -recursive", "terraform validate", "tflint --recursive", "terraform test",
                   "gitleaks git", "rhysd/actionlint", "python-version: '3.12'", "node-version: '24'"):
        assert needle in text, needle
