"""Every client's live engagements in a few reads instead of one per client. [08.1b]

The portfolio page asked the claims store for each client's engagement scopes one client at a time: with thousands of
accounts that is thousands of round trips per page view (an N+1). This reads them in batches of 500 clients.

It sits beside the claim repositories rather than in them: it needs their connection and nothing else, and it returns None for a
repository it does not know, so the page falls back to the per-client read (which also reports a failure per client).
In the Warehouse a batch spans clients by design, so it is an explicit, logged `tenant_exempt` read.
"""
from __future__ import annotations

from typing import Any

from domain.claims import EngagementScope, ProgramEngagement

_CHUNK = 500


def _engagement(row: Any, instant) -> ProgramEngagement:
    return ProgramEngagement(
        client_id=int(row["client_id"]), program_code=row["program_code"], scope=EngagementScope(row["scope"]),
        effective_from=instant(row["effective_from"]), effective_to=instant(row["effective_to"]),
        note=row["note"], set_by=row["set_by"], set_at=instant(row["set_at"]),
    )


def _sqlite(repo: Any, wanted: list[int]) -> dict[int, list[ProgramEngagement]]:
    from infrastructure.persistence.sqlite_claims import _parse_dt

    out: dict[int, list[ProgramEngagement]] = {i: [] for i in wanted}
    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start:start + _CHUNK]
        rows = repo._connect().execute(
            f"SELECT * FROM program_engagement WHERE client_id IN ({','.join('?' * len(chunk))}) AND effective_to IS NULL "
            "ORDER BY client_id, program_code", chunk).fetchall()
        for row in rows:
            out[int(row["client_id"])].append(_engagement(row, _parse_dt))
    return out


def _warehouse(repo: Any, wanted: list[int]) -> dict[int, list[ProgramEngagement]]:
    from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA
    from infrastructure.persistence.tenant_sql import tenant_exempt
    from infrastructure.persistence.warehouse_claims import _ENGAGEMENT_COLUMNS, from_db_instant, rows_as_dicts

    out: dict[int, list[ProgramEngagement]] = {i: [] for i in wanted}
    for start in range(0, len(wanted), _CHUNK):
        chunk = wanted[start:start + _CHUNK]
        sql = (f"SELECT {', '.join(_ENGAGEMENT_COLUMNS)} FROM {OPS_SCHEMA}.program_engagement "
               f"WHERE client_id IN ({','.join('?' * len(chunk))}) AND effective_to IS NULL ORDER BY client_id, program_code")
        with repo._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                tenant_exempt("the portfolio reads every listed client's engagements in one batch").execute(cursor, sql, chunk)
                for row in rows_as_dicts(cursor):
                    out[int(row["client_id"])].append(_engagement(row, from_db_instant))
            finally:
                cursor.close()
    return out


class EngagementBatchReader:
    """`read(repo, client_ids)`: {client: [engagements]} for every id asked (empty list when none), or None if unsupported."""

    def read(self, repo: Any, client_ids: list[int]) -> dict[int, list[ProgramEngagement]] | None:
        wanted = sorted({int(i) for i in client_ids})
        if hasattr(repo, "_connection"):
            return _warehouse(repo, wanted)
        if hasattr(repo, "_connect"):
            return _sqlite(repo, wanted)
        return None
