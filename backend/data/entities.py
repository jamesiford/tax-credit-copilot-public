"""Legal-entity (FEIN) registry for MeridianCore Logistics.

Maps each Employer FEIN that appears in the pay-period feed to a human-readable
legal-entity name, so the One/Zero per-FEIN breakdown (CALC-06 / I1) and the
entity-combination view (I2) read as real companies rather than bare tax IDs.

MeridianCore's Georgia footprint spans two legal entities — the parent operating
company and the Savannah distribution subsidiary — which is what makes the
legal-entity slicing and the "can these be combined?" question meaningful. Other
states currently file under a single entity.
"""
from __future__ import annotations

ENTITY_NAME_BY_FEIN: dict[str, str] = {
    "58-1234567": "MeridianCore Logistics LLC",
    "58-2233445": "MeridianCore Distribution GA, Inc.",
    "13-7654321": "MeridianCore Logistics LLC",
    "57-2345678": "MeridianCore Logistics LLC",
    "75-3456789": "MeridianCore Logistics LLC",
    "56-4567890": "MeridianCore Logistics LLC",
    "62-5678901": "MeridianCore Logistics LLC",
    "59-6789012": "MeridianCore Logistics LLC",
    "31-7890123": "MeridianCore Logistics LLC",
    "84-8901234": "MeridianCore Logistics LLC",
    "54-9012345": "MeridianCore Logistics LLC",
}


def entity_name(fein: str) -> str:
    """Return the legal-entity name for a FEIN, or the FEIN itself if unknown."""
    return ENTITY_NAME_BY_FEIN.get(fein, fein)
