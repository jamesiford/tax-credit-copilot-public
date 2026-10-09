"""The customer's source schema shape (internally codenamed "FlexSchema").

The engine reads the Silver Record Layout. The customer hands us their `intranet`
schema. This package holds the shape, the projection between them, and the
fixtures that let both be tested before the real feed arrives.

    schema.py       source schema table definitions (mirrors FlexSchema.txt)
    from_reference.py  reference CSVs -> the source shape, as "Candle Bottle"
    synth.py        additional synthetic clients in the same shape
    to_bcs.py       source shape -> Silver Record Layout (the Silver projection)

`tests/test_source_roundtrip.py` asserts the projection is lossless: the
reference dataset routed through the source shape must still yield 10,236
employees, 539 Min-Max and 656 Pay Period.
"""
from __future__ import annotations

from .schema import SourceDataset
from .from_fabric import FabricLakehouseReader
from .from_reference import REFERENCE_ACCOUNT_ID, REFERENCE_ACCOUNT_NAME, build_reference_source_dataset
from .synth import SYNTHETIC_CLIENTS, build_all_synthetic, build_synthetic_dataset
from .to_bcs import source_to_bcs_rows, projection_controls

__all__ = [
    "FabricLakehouseReader",
    "SourceDataset",
    "REFERENCE_ACCOUNT_ID",
    "REFERENCE_ACCOUNT_NAME",
    "SYNTHETIC_CLIENTS",
    "build_all_synthetic",
    "build_reference_source_dataset",
    "build_synthetic_dataset",
    "source_to_bcs_rows",
    "projection_controls",
]
