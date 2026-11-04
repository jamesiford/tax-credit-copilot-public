"""The Cowork skills' "go deeper" step: it teaches the data tools without loosening a single rule. [CH-16e]

The skill validator already refuses a name that is not a tool; these tests hold the new text to what it
promises. The workflow uses the three data tools, every dataset and column the reference table names
exists in the semantic model (so the skill cannot teach a column the catalog does not list), and the
verbatim and `verify_figures` rules the shared skill carries are still there, unchanged.
"""
from __future__ import annotations

import re

from test_cowork_package import _used, codes, errors, package, real, skill, stand_in_icons, validate_tools  # noqa: F401

from application.capabilities import catalog
from application.data.semantic_model import default_model

REVIEW = "skills/tcc-client-review-pack"
SHARED = "skills/tcc-figures-and-writes"
BACKTICKED = re.compile(r"`([a-z][a-z0-9_]*)`")


def model_names() -> set[str]:
    model = default_model()
    return {d.name for d in model.datasets} | {c.logical for d in model.datasets for c in d.columns}


def text(real, path: str) -> str:
    return real[2][path].decode("utf-8")


def test_the_review_pack_goes_deeper_with_the_three_data_tools(real):
    used = _used(real[2], "tcc-client-review-pack")
    assert {"data_catalog", "data_distinct_values", "data_query"} <= used


def test_the_go_deeper_step_is_optional_and_never_restates_a_fixed_figure(real):
    body = " ".join(text(real, f"{REVIEW}/SKILL.md").split())
    for must in ("Go deeper (optional", "authoritative for the credit, eligibility and trend", "never use `data_query` to restate",
                 "name every measure with `as`", "If the catalog has no column for the question, say so", "repeat that",
                 "unless the user is on the writer list"):
        assert must in body, must


def test_the_shared_rules_gain_a_data_section_and_keep_the_figure_rules(real):
    body = " ".join(text(real, f"{SHARED}/SKILL.md").split())
    for must in ("## 4. Questions about the data", "`data_catalog` first", "Never invent a column", "`employee_level_not_available`",
                 "exactly as the tool returned it", "VERBATIM", "`verify_figures`", "Never batch", "not tax advice"):
        assert must.lower() in body.lower(), must
    assert "Everything in section 1 applies unchanged" in body


def test_the_error_table_names_the_data_refusals(real):
    table = text(real, f"{SHARED}/references/error-messages.md")
    for code in ("employee_level_not_available", "query_timeout", "query_budget_exceeded", "column_not_listable"):
        assert f"`{code}`" in table, code


def test_every_name_in_the_questions_table_is_a_tool_or_something_the_catalog_lists(real):
    doc = text(real, f"{REVIEW}/references/data-questions.md")
    named = set(BACKTICKED.findall(doc))
    unknown = named - model_names() - set(catalog.BY_NAME)
    assert not unknown, f"the skill teaches names the catalog does not list: {sorted(unknown)}"
    assert {"unit_month_summary", "employee_eligibility", "unit_year_master", "run_method_summary"} <= named
    assert len(re.findall(r"^\| ", doc, re.MULTILINE)) >= 11, "a header, a rule and at least nine questions"


def test_every_tool_the_table_names_is_the_authority_or_a_step_and_exists(real):
    doc = text(real, f"{REVIEW}/references/data-questions.md")
    tools = {t for t in BACKTICKED.findall(doc) if t in catalog.BY_NAME}
    assert {"client_eligibility", "client_trend", "client_at_risk", "calc_walkthrough", "data_query", "data_catalog"} <= tools
    assert all(catalog.BY_NAME[t].implemented for t in tools)


def test_the_real_package_still_validates_with_the_new_text(real):
    configured, manifest, files = real
    assert not errors(package.validate(manifest, files, configured))


def test_a_skill_may_name_a_dataset_and_a_data_error_code_but_not_an_invented_one():
    assert not codes(validate_tools(skill("a-skill", "Read `employee_eligibility`, then `data_query`; expect `employee_level_not_available`.")))
    assert "TCC-T001" in codes(validate_tools(skill("a-skill", "Call `data_querry` first.")))
    assert "TCC-T001" in codes(validate_tools(skill("a-skill", "Use `employee_wages` for it.")))


def test_the_review_pack_body_stays_inside_the_token_budget(real):
    for name in ("tcc-client-review-pack", "tcc-figures-and-writes"):
        assert len(text(real, f"skills/{name}/SKILL.md")) / 4 < 5000, name
