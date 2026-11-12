"""Which account the certified reference run is about: configuration, never a constant.

The reference dataset is a conformance fixture. A deployment that holds it names its account in
`REFERENCE_ACCOUNT_ID`; one that does not has no sealed run, and asking for it is a typed,
explained 503 rather than a read of whichever client happens to share an id.
"""
from __future__ import annotations

from config import get_settings

DEFAULT_REFERENCE_LABEL = "Reference Dataset Client"


def reference_account_id() -> int | None:
    return get_settings().data_source.reference_account_id


def reference_account_name() -> str:
    return get_settings().data_source.reference_account_name or DEFAULT_REFERENCE_LABEL


def require_reference_account_id() -> int:
    """The configured reference account, or `ReferenceNotConfigured`."""
    account_id = reference_account_id()
    if account_id is None:
        from application.errors import ReferenceNotConfigured

        raise ReferenceNotConfigured()
    return account_id
