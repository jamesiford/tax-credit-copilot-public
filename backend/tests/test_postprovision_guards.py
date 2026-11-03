"""postprovision must never overwrite a brought Lakehouse. [CH-13]

`data.source.load_fabric --synthetic-only` OVERWRITES every table it writes, which drops the
reference client from a Lakehouse that already holds it. The step belongs to a Lakehouse Terraform
just created (`TCC_FABRIC_CREATED=true`), and to nothing else, whatever the profile says.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "postprovision.ps1"


def test_the_synthetic_load_runs_only_against_a_lakehouse_terraform_created():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("load-synthetic' {")
    guard = text[text.rindex("if (", 0, start):start]
    assert "$env:TCC_PROFILE -eq 'public'" in guard
    assert "$created" in guard, "the load must be conditional on TCC_FABRIC_CREATED"


def test_the_destructive_bootstrap_is_still_gated_on_a_created_warehouse():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "if ($created)" in text and "--bootstrap" in text
