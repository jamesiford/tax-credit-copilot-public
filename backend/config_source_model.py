"""Settings for how the source is mapped and checked. [06]

Kept out of `config_sections.py`, which is at its size limit. All four are optional: with none set the
shipped default mapping applies, the boot check only warns, and the named transforms take the mapping's
own value.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from config_values import choice as _choice

#: Named transforms and the values each accepts (`data/source/mapping/transforms.py`).
WORKSITE_SOURCES = ("worksite_then_location", "location_only", "worksite_only")
NULL_PAY_DATE_POLICIES = ("period_end", "exclude")
VALIDATION_MODES = ("off", "warn", "fail")


@dataclass(frozen=True)
class SourceModelSettings:
    """The mapping file and the transform choices that override it."""

    mapping_file: str | None = None
    validation: str = "warn"
    worksite_source: str | None = None
    null_pay_date: str | None = None


def parse_source_model(environ: Mapping[str, str]) -> SourceModelSettings:
    def optional(name: str, allowed: tuple[str, ...]) -> str | None:
        return _choice(environ, name, allowed, allowed[0]) if environ.get(name, "").strip() else None

    return SourceModelSettings(
        mapping_file=(environ.get("SOURCE_MAPPING_FILE") or "").strip() or None,
        validation=_choice(environ, "SOURCE_SCHEMA_VALIDATION", VALIDATION_MODES, "warn"),
        worksite_source=optional("WORKSITE_LOCATION_SOURCE", WORKSITE_SOURCES),
        null_pay_date=optional("NULL_PAY_DATE_POLICY", NULL_PAY_DATE_POLICIES),
    )
