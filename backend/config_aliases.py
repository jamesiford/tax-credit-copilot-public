"""One-release fallbacks for environment variables renamed away from the product prefix.

The product name is the customer's to change, so no variable carries it. A host that still
has the old name in its environment keeps working: `with_aliases` copies the old value to
the new name when the new name is unset, and the new name always wins when both are set.
Only the NAME of a deprecated variable is ever logged, never its value.

This table is the one place the old names live for the Python backend and its scripts.
To drop the aliases next release: delete the table, `with_aliases` and `warn_deprecated`,
and the call in `config.load_settings`.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping

#: new name -> the `TCC_` name it replaces.
ALIASES: Mapping[str, str] = {
    "ALLOW_SEED": "TCC_ALLOW_SEED",
    "KEEPALIVE_SECONDS": "TCC_KEEPALIVE_SECONDS",
    "STRANDED_RUN_MINUTES": "TCC_STRANDED_RUN_MINUTES",
    "WARM_CLIENTS": "TCC_WARM_CLIENTS",
    "WARM_ON_START": "TCC_WARM_ON_START",
    "REPOSITORY_ROOT": "TCC_REPO_ROOT",
    "FABRIC_CREATED": "TCC_FABRIC_CREATED",
    "SQL_CREATED": "TCC_SQL_CREATED",
    "BACKEND_DIR": "TCC_BACKEND",
    "TEST_FABRIC": "TCC_FABRIC_TESTS",
    "TEST_SQL": "TCC_SQL_TESTS",
    "TEST_AZURE": "TCC_AZURE_TESTS",
    "TEST_REQUIRE_PARITY": "TCC_REQUIRE_PARITY",
    "TEST_SETTINGS_PROBE": "TCC_TEST_SETTINGS_PROBE",
    "TEST_SCHEMA": "TCC_TEST_SCHEMA",
    "TEST_AI_EVALS_LIVE": "TCC_AI_EVALS_LIVE",
    "TEST_ENV_FILE": "TCC_ENV_FILE",
    "TEST_UPDATE_DEVIATIONS": "TCC_UPDATE_DEVIATIONS",
}

#: The Cowork plugin reads `<prefix><KEY>` for every key it knows.
COWORK_PREFIX = "COWORK_"
LEGACY_COWORK_PREFIX = "TCC_COWORK_"

_LOG = logging.getLogger("config.aliases")
_warned: set[str] = set()


def deprecated_in_use(environ: Mapping[str, str]) -> tuple[str, ...]:
    """The old names that currently supply a value (their new name is unset)."""
    return tuple(old for new, old in ALIASES.items() if new not in environ and old in environ)


def with_aliases(environ: Mapping[str, str]) -> dict[str, str]:
    """A copy of `environ` in which an unset new name takes the value of its old name."""
    resolved = dict(environ)
    for new, old in ALIASES.items():
        if new not in resolved and old in resolved:
            resolved[new] = resolved[old]
    return resolved


def warn_deprecated(environ: Mapping[str, str]) -> None:
    """Log one line per deprecated name, once per process. The line names the variable, never its value."""
    for old in deprecated_in_use(environ):
        if old not in _warned:
            _warned.add(old)
            new = next(n for n, o in ALIASES.items() if o == old)
            _LOG.warning("Deprecated environment variable %s is in use; set %s instead.", old, new)


def env_value(environ: Mapping[str, str], name: str, default: str = "") -> str:
    """`environ[name]`, else the value of its deprecated alias (warning once), else `default`."""
    if name in environ:
        return environ[name]
    old = ALIASES.get(name)
    if old is not None and old in environ:
        warn_deprecated(environ)
        return environ[old]
    return default


def apply_to_process(environ: MutableMapping[str, str]) -> None:
    """Copy old values to new names in a process environment (test and script setup), warning once per name."""
    warn_deprecated(environ)
    for new, old in ALIASES.items():
        if new not in environ and old in environ:
            environ[new] = environ[old]
