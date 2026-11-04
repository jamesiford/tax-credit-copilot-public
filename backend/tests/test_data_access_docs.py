"""The data-access settings are mapped, documented and consistent everywhere. [CH-16f]

A setting that exists in code but not in Terraform cannot be set on a deployed API; one in Terraform
that the code never reads is a lie; one in neither document is a surprise. These tests keep the four
places (code, Terraform, azd mapping, ENV-VARS) and the page that explains them in step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_SETTINGS = {
    "DATA_QUERY_SOURCE_ENABLED": "data_query_source_enabled",
    "DATA_QUERY_TIMEOUT_SECONDS": "data_query_timeout_seconds",
    "DATA_QUERY_MAX_ROWS": "data_query_max_rows",
    "DATA_QUERY_RATE_PER_MINUTE": "data_query_rate_per_minute",
    "DATA_QUERY_MAX_CONCURRENCY": "data_query_max_concurrency",
    "LAKEHOUSE_SQL_SERVER": "lakehouse_sql_server",
    "LAKEHOUSE_SQL_DATABASE": "lakehouse_sql_database",
}


def read(*parts: str) -> str:
    return REPO.joinpath(*parts).read_text(encoding="utf-8")


def test_every_setting_the_data_query_reads_is_mapped_from_a_terraform_variable():
    main = read("infra", "main.tf")
    variables = read("infra", "variables.tf")
    for setting, variable in DATA_SETTINGS.items():
        assert re.search(rf"\b{setting}\b", main), f"{setting} is not emitted by infra/main.tf"
        assert f'variable "{variable}"' in variables, f"no Terraform variable {variable}"


def test_the_terraform_settings_are_the_ones_the_code_reads():
    code = read("backend", "application", "data_wiring.py") + read(
        "backend", "infrastructure", "persistence", "lakehouse_sql_connection.py"
    )
    for setting in DATA_SETTINGS:
        assert setting in code, f"{setting} is set by Terraform but read by nothing"


def test_each_variable_has_an_azd_value_and_the_source_flag_defaults_to_false():
    mapping = json.loads(read("infra", "main.tfvars.json"))
    for variable in DATA_SETTINGS.values():
        assert variable in mapping, f"{variable} has no azd value in main.tfvars.json"
        assert re.fullmatch(r"\$\{TCC_[A-Z_]+(=[a-z]+)?\}", mapping[variable])
    assert mapping["data_query_source_enabled"] == "${TCC_DATA_QUERY_SOURCE_ENABLED=false}"


def test_the_flag_is_emitted_only_when_true_so_a_default_plan_is_unchanged():
    main = read("infra", "main.tf")
    assert "var.data_query_source_enabled ? { DATA_QUERY_SOURCE_ENABLED" in main
    assert re.search(r'variable "data_query_source_enabled" \{[^}]*default\s*=\s*false', read("infra", "variables.tf"), re.S)


def test_the_gateway_module_is_given_no_data_query_setting():
    channel = read("infra", "modules", "channel", "main.tf")
    assert "DATA_QUERY" not in channel and "LAKEHOUSE_SQL" not in channel


def test_env_vars_documents_every_setting_and_its_azd_value():
    text = read("docs", "architecture", "ENV-VARS.md")
    for setting, variable in DATA_SETTINGS.items():
        assert f"`{setting}`" in text, f"ENV-VARS.md does not list {setting}"
        assert f"`{variable}`" in text, f"ENV-VARS.md does not name the Terraform variable {variable}"
    assert "TCC_DATA_QUERY_SOURCE_ENABLED" in text


def test_the_data_access_page_is_indexed_and_covers_what_the_work_package_promised():
    readme = read("docs", "m365-channel", "README.md")
    assert "DATA-ACCESS.md" in readme
    page = read("docs", "m365-channel", "DATA-ACCESS.md")
    for heading in (
        "The two lanes", "Limits", "Audit and provenance", "What is and is not queryable",
        "Adding a dataset or a column", "Operational notes", "Grants the lakehouse endpoint needs",
        "Evaluation: a Microsoft Fabric Data Agent",
    ):
        assert heading in page, f"DATA-ACCESS.md lost its section {heading!r}"
    assert "test_semantic_model_drift.py" in page, "the page must name the drift test that forces the decision"


def test_the_security_posture_names_the_data_path_and_the_gateway_has_no_grant():
    security = read("SECURITY.md")
    assert "Governed data queries" in security
    assert "channel gateway has no grant" in security
    matrix = read("docs", "architecture", "CONNECTIVITY-MATRIX.md")
    assert "R5a" in matrix and "CH10" in matrix
