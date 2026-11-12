"""The source mapping: a declarative description of where each logical field lives. [06]

`resolver` is what consumers import; `model` is the typed shape and the loader; `transforms` holds the
named meanings a mapping can select; `validate` compares a mapping with a real lake.
"""
from . import validate
from .model import MappingError, SourceMapping, parse_mapping
from .resolver import (
    column, default_mapping, describe, mapping, null_pay_date_mode, optional_tables, partition_columns,
    physical_table, quoted, spec, table_map, tenant_column, tenant_columns, worksite_mode,
)

__all__ = [
    "MappingError", "SourceMapping", "column", "default_mapping", "describe", "mapping", "null_pay_date_mode",
    "optional_tables", "parse_mapping", "partition_columns", "physical_table", "quoted", "spec", "table_map",
    "tenant_column", "tenant_columns", "validate", "worksite_mode",
]
