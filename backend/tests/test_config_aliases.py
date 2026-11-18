"""The one-release fallbacks for the renamed `TCC_` environment variables."""
from __future__ import annotations

import logging

import pytest

import config_aliases
from config import load_settings

SECRET = "s3cret-value-that-must-never-be-logged"


@pytest.fixture(autouse=True)
def _fresh_warnings():
    config_aliases._warned.clear()
    yield
    config_aliases._warned.clear()


@pytest.mark.parametrize("new,old", sorted(config_aliases.ALIASES.items()))
def test_every_alias_resolves_the_old_name(new, old):
    assert load_settings({old: "1"}).environ[new] == "1"


@pytest.mark.parametrize("new,old", sorted(config_aliases.ALIASES.items()))
def test_the_new_name_wins_when_both_are_set(new, old):
    assert load_settings({new: "new", old: "old"}).environ[new] == "new"


def test_the_old_name_is_deprecated_only_while_it_supplies_the_value():
    assert config_aliases.deprecated_in_use({"TCC_WARM_ON_START": "0"}) == ("TCC_WARM_ON_START",)
    assert config_aliases.deprecated_in_use({"TCC_WARM_ON_START": "0", "WARM_ON_START": "1"}) == ()


def test_the_warning_names_the_variable_once_and_never_the_value(caplog):
    caplog.set_level(logging.WARNING, logger="config.aliases")
    environ = {"TCC_ALLOW_SEED": SECRET}
    load_settings(environ)
    load_settings(environ)
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "TCC_ALLOW_SEED" in messages[0] and "ALLOW_SEED" in messages[0]
    assert SECRET not in caplog.text


def test_a_setting_is_parsed_from_the_old_name():
    assert load_settings({"TCC_WARM_ON_START": "0"}).runtime.warm_on_start is False
    assert load_settings({"TCC_WARM_ON_START": "0", "WARM_ON_START": "1"}).runtime.warm_on_start is True


def test_env_value_prefers_the_new_name_then_the_old_then_the_default():
    assert config_aliases.env_value({"SQL_CREATED": "a", "TCC_SQL_CREATED": "b"}, "SQL_CREATED") == "a"
    assert config_aliases.env_value({"TCC_SQL_CREATED": "b"}, "SQL_CREATED") == "b"
    assert config_aliases.env_value({}, "SQL_CREATED", "none") == "none"


def test_apply_to_process_fills_only_unset_names():
    environ = {"TCC_FABRIC_TESTS": "1", "TCC_SQL_TESTS": "1", "TEST_SQL": "0"}
    config_aliases.apply_to_process(environ)
    assert environ["TEST_FABRIC"] == "1" and environ["TEST_SQL"] == "0"
