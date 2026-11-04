"""One reader of the environment, and a typed settings object everything else is handed. [RM-20, D-142]

Before RM-20 about sixty `os.environ` / `os.getenv` reads were spread over thirty files,
so the question "what does this process read, and what happens when it is unset" had no
single answer and a default could be changed in one place and not another. Now
`config.py` is the only module that touches the process environment. Everything else
receives a typed section of `Settings` (`get_settings()`), or a mapping that came from it.

The allow-list below is pinned exactly: an entry whose file stops reading the environment
fails the test, so it can only shrink. The composition root (`bootstrap/`) is NOT exempt:
it asks `config` like every other module, which is stricter than the work package required.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import config
import config_sections
from config import get_settings, load_settings, override_settings, resolve_environ, set_settings

BACKEND = Path(__file__).resolve().parent.parent

#: The one module that reads the process environment.
THE_READER = "config.py"

#: Genuinely process-level readers, each with the reason it cannot ask `config`. Exact; may only shrink.
ALLOWED_PROCESS_READERS = {
    "tools/verify_reference_independent.py": (
        "the independent reference check was written WITHOUT reference to the implementation, so a "
        "tie-out against the partner's figures cannot share a settings object with the code it checks; "
        "it reads one variable (the fixture root) and imports no backend module"
    ),
}

_OS_NAMES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"})


def _production_files() -> list[Path]:
    skipped = {"tests", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
    return sorted(p for p in BACKEND.rglob("*.py") if not skipped & set(p.relative_to(BACKEND).parts))


def process_reads(source: str) -> list[int]:
    """Line of every use of the process environment: `os.environ`, `os.getenv`, `from os import environ`."""
    tree = ast.parse(source)
    os_aliases = {"os"}
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_aliases.update(a.asname for a in node.names if a.name == "os" and a.asname)
        elif isinstance(node, ast.ImportFrom) and node.module == "os" and node.level == 0:
            lines.extend(node.lineno for a in node.names if a.name in _OS_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _OS_NAMES:
            if isinstance(node.value, ast.Name) and node.value.id in os_aliases:
                lines.append(node.lineno)
    return sorted(set(lines))


def _offenders() -> dict[str, list[int]]:
    found = {}
    for path in _production_files():
        relative = path.relative_to(BACKEND).as_posix()
        lines = process_reads(path.read_text(encoding="utf-8"))
        if lines and relative != THE_READER:
            found[relative] = lines
    return found


# --------------------------------------------------------------------- the rule


def test_only_config_reads_the_process_environment():
    unexpected = {f: lines for f, lines in _offenders().items() if f not in ALLOWED_PROCESS_READERS}
    assert not unexpected, (
        "production code reads the process environment outside config.py:\n  "
        + "\n  ".join(f"{f}:{lines}" for f, lines in unexpected.items())
        + "\n\nAdd a typed field to a section in config_sections.py and read `get_settings()`; a parser that "
        "must stay independent of this module takes a mapping, which the composition root gets from "
        "`get_settings().environ`."
    )


def test_the_allow_list_is_exact_and_can_only_shrink():
    assert set(_offenders()) == set(ALLOWED_PROCESS_READERS), (
        "an allow-listed reader no longer reads the environment (remove its entry), or a reader was "
        "added to the list without being one"
    )
    assert all(reason.strip() for reason in ALLOWED_PROCESS_READERS.values())


def test_config_is_the_reader_and_its_sections_are_pure_parsers():
    assert process_reads((BACKEND / THE_READER).read_text(encoding="utf-8"))
    assert not process_reads((BACKEND / "config_sections.py").read_text(encoding="utf-8")), (
        "config_sections.py parses a mapping it is given; only config.py touches the process"
    )


@pytest.mark.parametrize("source,expected", [
    ("import os\nx = os.environ['A']\n", [2]),
    ("import os\nx = os.getenv('A')\n", [2]),
    ("import os as o\nx = o.environ.get('A')\n", [2]),
    ("from os import environ\n", [1]),
    ("from os import getenv as g\n", [1]),
    ("import os\nx = os.environ\n", [2]),
    ("import os\nos.putenv('A', 'b')\n", [2]),
    ("def f(environ):\n    return environ['A']\n", []),
    ("import os\nx = os.path.join('a')\n", []),
    ('"""mentions os.environ in a docstring"""\n', []),
])
def test_the_detector_finds_each_way_of_reading_the_process_environment(source, expected):
    assert process_reads(source) == expected


def test_the_vendored_shared_modules_do_not_import_config():
    """The orchestrator copies these and cannot import `backend`; they take a mapping instead."""
    seeds = ["application/ai/settings.py", "application/ai/gateway_settings.py", "application/knowledge/settings.py"]
    for relative in seeds:
        tree = ast.parse((BACKEND / relative).read_text(encoding="utf-8"))
        imported = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        imported |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert "config" not in imported and "config_sections" not in imported, relative


# --------------------------------------------------------------------- the object


def test_get_settings_rereads_the_environment_on_every_call(monkeypatch):
    monkeypatch.delenv("TCC_TEST_SETTINGS_PROBE", raising=False)
    assert "TCC_TEST_SETTINGS_PROBE" not in get_settings().environ
    monkeypatch.setenv("TCC_TEST_SETTINGS_PROBE", "one")
    assert get_settings().environ["TCC_TEST_SETTINGS_PROBE"] == "one"
    monkeypatch.setenv("TCC_TEST_SETTINGS_PROBE", "two")
    assert get_settings().environ["TCC_TEST_SETTINGS_PROBE"] == "two"


def test_settings_are_a_frozen_snapshot_of_what_they_were_built_from():
    source = {"LOG_LEVEL": "DEBUG"}
    settings = load_settings(source)
    source["LOG_LEVEL"] = "ERROR"
    assert settings.runtime.log_level == "DEBUG"
    with pytest.raises(TypeError):
        settings.environ["LOG_LEVEL"] = "x"  # type: ignore[index]
    with pytest.raises(AttributeError):
        settings.environ = {}  # type: ignore[misc]


def test_override_settings_installs_fixed_values_and_restores_the_previous():
    assert config._override is None
    with override_settings({"LOG_LEVEL": "WARNING"}) as fixed:
        assert get_settings() is fixed and get_settings().runtime.log_level == "WARNING"
        with override_settings({"LOG_LEVEL": "ERROR"}):
            assert get_settings().runtime.log_level == "ERROR"
        assert get_settings().runtime.log_level == "WARNING"
    assert config._override is None


def test_set_settings_none_returns_to_the_environment(monkeypatch):
    set_settings(load_settings({"LOG_LEVEL": "CRITICAL"}))
    try:
        assert get_settings().runtime.log_level == "CRITICAL"
    finally:
        set_settings(None)
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    assert get_settings().runtime.log_level == "INFO"


def test_resolve_environ_prefers_what_it_is_handed():
    handed = {"A": "1"}
    assert resolve_environ(handed) is handed
    with override_settings({"A": "2"}):
        assert resolve_environ()["A"] == "2"


def test_a_bad_value_in_one_section_does_not_break_another():
    """Sections are parsed on first use, as each scattered reader parsed its own variable."""
    settings = load_settings({"TCC_STRANDED_RUN_MINUTES": "soon", "LOG_LEVEL": "DEBUG"})
    assert settings.runtime.log_level == "DEBUG"
    with pytest.raises(ValueError):
        settings.warehouse
    assert settings.stores.operational_db_or("x") == "x"


# --------------------------------------------------------------------- the defaults


def test_every_default_is_the_value_the_reader_used_before():
    settings = load_settings({})
    assert settings.runtime == config_sections.RuntimeSettings(None, "INFO", True, 30)
    assert settings.observability == config_sections.ObservabilitySettings(None, None, None)
    source = settings.data_source
    assert (source.data_source, source.explicit_data_source, source.fabric_employees_table, source.flex_account_id) == (
        "lakehouse", None, "dbo/employees", 1001)
    warehouse = settings.warehouse
    assert (warehouse.server, warehouse.database, warehouse.odbc_driver, warehouse.connect_timeout,
            warehouse.stranded_run_minutes) == ("", "", "ODBC Driver 18 for SQL Server", 90, 60)
    stores = settings.stores
    assert (stores.operational_db, stores.artifact_local_root, stores.artifact_blob_account_url,
            stores.outputs_retention_days, stores.claim_store) == (None, None, "", 2555, "sqlite")
    assert settings.webiq == config_sections.WebIqSettings(None, None, None)


def test_values_are_parsed_to_their_types():
    settings = load_settings({
        "TCC_WARM_ON_START": " No ", "TCC_KEEPALIVE_SECONDS": "2", "DATA_SOURCE": " CSV ", "FLEX_ACCOUNT_ID": "42",
        "WAREHOUSE_CONNECT_TIMEOUT": "7", "OUTPUTS_RETENTION_DAYS": "30", "WEBIQ_API_KEY": "", "OPERATIONAL_DB": "",
    })
    assert settings.runtime.warm_on_start is False
    assert settings.runtime.keepalive_seconds == 5, "never below 5 seconds"
    assert settings.data_source.data_source == "csv" and settings.data_source.flex_account_id == 42
    assert settings.warehouse.connect_timeout == 7 and settings.stores.outputs_retention_days == 30
    assert settings.webiq.api_key is None
    assert settings.stores.operational_db_or("fallback") == "", "set-but-empty stays empty, as os.getenv had it"


def test_an_unparseable_keepalive_is_the_default_and_an_unparseable_number_elsewhere_raises():
    assert load_settings({"TCC_KEEPALIVE_SECONDS": "often"}).runtime.keepalive_seconds == 30
    for name, section in (("FLEX_ACCOUNT_ID", "data_source"), ("WAREHOUSE_CONNECT_TIMEOUT", "warehouse"),
                          ("OUTPUTS_RETENTION_DAYS", "stores")):
        with pytest.raises(ValueError):
            getattr(load_settings({name: "x"}), section)


def test_the_lakehouse_and_warehouse_fall_back_in_the_order_the_connection_always_used():
    settings = load_settings({"WAREHOUSE_SERVER": "w", "LAKEHOUSE_SQL_SERVER": "l", "FABRIC_LAKEHOUSE": "lh"})
    assert settings.warehouse.lakehouse_sql_server == "l" and settings.warehouse.server == "w"
    assert settings.data_source.fabric_lakehouse == "lh"


@pytest.mark.parametrize("value,ok", [("tcc_gold", True), (" custom ", True), ("a.b", False), ("1a", False), ("x; DROP", False)])
def test_schema_names_are_validated_where_they_are_parsed(value, ok):
    if ok:
        assert config_sections.parse_schema_name({"S": value}, "S", "d") == value.strip()
    else:
        with pytest.raises(ValueError):
            config_sections.parse_schema_name({"S": value}, "S", "d")
