"""The customer's source schema shape (internally codenamed "FlexSchema").

The engine reads the Silver Record Layout. The customer hands us their `intranet`
schema. This package holds the shape, the projection between them, and the
fixtures that let both be tested before the real feed arrives.

    schema.py       source schema table definitions (mirrors FlexSchema.txt)
    from_reference.py  reference CSVs -> the source shape, as "Candle Bottle"
    synth.py        additional synthetic clients in the same shape (a fixture, see below)
    to_bcs.py       source shape -> Silver Record Layout (the Silver projection)

`tests/test_source_roundtrip.py` asserts the projection is lossless: the
reference dataset routed through the source shape must still yield 10,236
employees, 539 Min-Max and 656 Pay Period.

**`synth.py` is a fixture, not runtime code.** It builds invented clients for tests and for the
public profile's synthetic load (`load_fabric --synthetic-only`, run by postprovision). It stays in
this package because that loader ships with the backend, but no runtime path imports it:
`SYNTHETIC_CLIENTS`, `build_all_synthetic` and `build_synthetic_dataset` are resolved lazily below, so
importing `data.source` does not load it. `tests/test_architecture_fixtures.py` enforces both halves.
"""
from __future__ import annotations

from .schema import SourceDataset
from .from_fabric import FabricLakehouseReader
from .from_reference import REFERENCE_ACCOUNT_ID, REFERENCE_ACCOUNT_NAME, build_reference_source_dataset
from .to_bcs import source_to_bcs_rows, projection_controls

_LAZY_SYNTH = ("SYNTHETIC_CLIENTS", "build_all_synthetic", "build_synthetic_dataset")


def __getattr__(name: str):
    """Resolve the synthetic-fixture names on first use, so the runtime import never loads synth.py."""
    if name in _LAZY_SYNTH:
        from . import synth

        return getattr(synth, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FabricLakehouseReader",
    "SourceDataset",
    "REFERENCE_ACCOUNT_ID",
    "REFERENCE_ACCOUNT_NAME",
    "build_reference_source_dataset",
    "source_to_bcs_rows",
    "projection_controls",
]
