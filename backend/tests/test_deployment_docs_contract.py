"""Every deployment knob an operator can set must be documented.

The customer's platform team stands this up from
`docs/architecture/DEPLOYMENT-HANDOVER.md`. A value that reaches
`infra/main.tfvars.json` is something somebody has to decide, and an
undocumented one is a decision made silently by a default nobody read.

This is not hypothetical. `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` and
`RUN_MANIFEST_STORE` were once added without the handover saying so, and an
unset `WAREHOUSE_SERVER` made the landing page a 500 rather than a slow page.

The test reads the files as an operator would: what can I set, and where is
it explained. (Platform v2: Terraform replaced Bicep; azd maps environment
values through `infra/main.tfvars.json`.)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
TFVARS = REPO / "infra" / "main.tfvars.json"
VARIABLES = REPO / "infra" / "variables.tf"
HANDOVER = REPO / "docs" / "architecture" / "DEPLOYMENT-HANDOVER.md"

#: Set by azd itself rather than chosen by an operator.
WRITTEN_BY_AZD = {"AZURE_ENV_NAME", "AZURE_SUBSCRIPTION_ID"}


def _env_vars_by_variable() -> dict[str, str]:
    """Terraform variable -> the azd environment value that feeds it (`${NAME}` / `${NAME=default}`)."""
    declared = json.loads(TFVARS.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for variable, value in declared.items():
        found = re.search(r"\$\{([A-Z0-9_]+)", str(value))
        if found:
            mapping[variable] = found.group(1)
    return mapping


def test_every_settable_value_is_documented_in_the_handover():
    mapping = _env_vars_by_variable()
    assert mapping, (
        "No ${ENV_VAR} substitutions found in infra/main.tfvars.json. Either the "
        "file changed shape or this test's parser is stale."
    )
    handover = HANDOVER.read_text(encoding="utf-8")
    undocumented = sorted(e for e in mapping.values() if e not in WRITTEN_BY_AZD and e not in handover)
    assert not undocumented, (
        "azd environment values an operator can set, absent from "
        "docs/architecture/DEPLOYMENT-HANDOVER.md:\n  " + "\n  ".join(undocumented)
    )


def test_every_mapped_value_reaches_a_declared_variable():
    declared = set(re.findall(r'^variable "(\w+)"', VARIABLES.read_text(encoding="utf-8"), re.M))
    unknown = sorted(set(_env_vars_by_variable()) - declared)
    assert not unknown, f"main.tfvars.json maps values into undeclared variables: {unknown}"
