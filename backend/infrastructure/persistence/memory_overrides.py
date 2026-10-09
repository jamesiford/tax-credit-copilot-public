"""`ManualOverrideRepository` in process memory. CI and local development only.

The same bargain as `memory_runs.py`: nothing survives a restart, and the
instance says so (`is_durable = False`). A deployed environment reads and
writes `tcc_ops.manual_override`.
"""
from __future__ import annotations

from domain.warehouse import ManualOverride


def base_years_from(rows: list[ManualOverride], client_id: int, program_code: str) -> dict[str, int]:
    """Latest row per location wins; a cleared choice drops out. Shared by both adapters."""
    prefix = f"{program_code}:"
    latest: dict[str, ManualOverride] = {}
    for row in sorted(rows, key=lambda r: (r.created_at, r.override_id)):
        if row.client_id != client_id or row.field_changed != "base_year":
            continue
        if not row.target_key.startswith(prefix):
            continue
        latest[row.target_key[len(prefix):]] = row
    out: dict[str, int] = {}
    for worksite_id, row in latest.items():
        if row.value_after is not None:
            try:
                out[worksite_id] = int(row.value_after)
            except ValueError:
                continue
    return out


class InMemoryManualOverrideRepository:
    is_durable = False

    def __init__(self) -> None:
        self._rows: list[ManualOverride] = []

    def record(self, override: ManualOverride) -> ManualOverride:
        if any(r.override_id == override.override_id for r in self._rows):
            raise ValueError(f"override_id={override.override_id!r} is already recorded")
        self._rows.append(override)
        return override

    def base_years(self, client_id: int, program_code: str) -> dict[str, int]:
        return base_years_from(self._rows, client_id, program_code)

    def history(self, client_id: int) -> list[ManualOverride]:
        return sorted((r for r in self._rows if r.client_id == client_id), key=lambda r: r.created_at)
