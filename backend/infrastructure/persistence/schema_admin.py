"""Schema administration: the bootstrap, forward-only migrations, and the guard
that decides which Warehouse a script may touch. [D22, D27]

Three rules, and the reason for each:

**The bootstrap is destructive, so it runs at most once per Warehouse.** DDL
v2.0 drops and recreates every table. It runs only where there is no
`<ops>.schema_migration` table AND the target is approved for it: a Warehouse
Terraform has just created, or the one pinned demo Warehouse (D27). Every later
change is a numbered file under `docs/data/schema/migrations/`, applied once and
recorded. A re-run applies nothing.

**A script names its target, and the target is checked before any statement.**
The workspace and item are resolved through the Fabric REST API and compared to
an allow-list; the server we are about to connect to must be the endpoint that
resolution returned. A mismatch raises `TargetMismatch` and nothing executes.
Running destructive DDL against "whatever WAREHOUSE_SERVER happens to say" is
the failure this exists to make impossible.

**Validation queries are judged per result set.** DDL section 9 is a run of
SELECTs with no `GO` between them; each must return zero rows. A batch can carry
several result sets, so `run_batches` walks every one of them rather than
reading the first and calling the batch clean.

Nothing here reads `docs/`: the CLIs in `scripts/` pass file paths in.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_GOLD = "tcc_gold"
DEFAULT_OPS = "tcc_ops"
BOOTSTRAP_VERSION = "0000"

_GO_LINE = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE)
_MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9][a-z0-9_]*)\.sql$")


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------


def _strip_comments(sql: str) -> str:
    """The text with block and line comments removed. Strings are respected."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        two = sql[i:i + 2]
        if two == "/*":
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
        elif two == "--":
            end = sql.find("\n", i)
            i = n if end < 0 else end
        elif sql[i] == "'":
            end = i + 1
            while end < n:
                if sql[end] == "'" and sql[end + 1:end + 2] == "'":
                    end += 2
                    continue
                if sql[end] == "'":
                    break
                end += 1
            out.append(sql[i:end + 1])
            i = end + 1
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def is_blank(sql: str) -> bool:
    """True when nothing but whitespace and comments remains."""
    return not _strip_comments(sql).strip()


def split_batches(sql: str) -> list[str]:
    """Split T-SQL on `GO` separator lines, the way sqlcmd does.

    A `GO` inside a block comment is text, not a separator. Batches holding only
    comments are dropped: sending one is a round trip that does nothing.
    """
    batches: list[str] = []
    current: list[str] = []
    in_block = False
    for line in sql.splitlines():
        if not in_block and _GO_LINE.match(line):
            batches.append("\n".join(current))
            current = []
            continue
        current.append(line)
        # Track block-comment state across lines (strings never span a GO).
        scan = _strip_line_strings(line)
        pos = 0
        while True:
            if in_block:
                end = scan.find("*/", pos)
                if end < 0:
                    break
                in_block, pos = False, end + 2
            else:
                start = scan.find("/*", pos)
                line_comment = scan.find("--", pos)
                if start < 0 or (0 <= line_comment < start):
                    break
                in_block, pos = True, start + 2
    batches.append("\n".join(current))
    return [b.strip("\n") for b in batches if not is_blank(b)]


def _strip_line_strings(line: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", line)


def split_statements(sql: str) -> list[str]:
    """Split a GO-free run of statements on terminating semicolons.

    For the validation section, so each query is executed and reported on its
    own. A `;` inside a comment or string does not split.
    """
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        current.append(line)
        code = _strip_comments(_strip_line_strings(line)).rstrip()
        if code.endswith(";"):
            statements.append("\n".join(current))
            current = []
    if current:
        statements.append("\n".join(current))
    return [s.strip("\n") for s in statements if not is_blank(s)]


def statement_label(statement: str) -> str:
    """The `-- 9.x` heading a validation query carries, or its first code line."""
    for line in statement.splitlines():
        match = re.match(r"^\s*--\s*(\d+\.\d+[a-z]?)\b(.*)$", line)
        if match:
            return f"{match.group(1)}{match.group(2)}".strip()
    code = [l.strip() for l in _strip_comments(statement).splitlines() if l.strip()]
    return code[0][:80] if code else "(empty)"


# --------------------------------------------------------------------------
# Sections of the DDL file
# --------------------------------------------------------------------------


def _section_header(number: str) -> re.Pattern[str]:
    # A rule of '=' then "N. TITLE". The rule may open a comment ("/* ====") or
    # sit inside one: section 9 shares its comment block with section 8.
    return re.compile(r"^[ \t]*(?:/\*)?[ \t]*=+[ \t]*\n[ \t]*" + re.escape(number) + r"\.\s", re.MULTILINE)


_ANY_SECTION = re.compile(r"^[ \t]*(?:/\*)?[ \t]*=+[ \t]*\n[ \t]*\d+\.\s", re.MULTILINE)


def extract_section(sql: str, number: str) -> str:
    """The code under a top-level `==== N. TITLE ====` header.

    Runs from the end of the comment holding that header to the start of the
    next top-level header (or the end of the file).
    """
    header = _section_header(number).search(sql)
    if not header:
        raise ValueError(f"section {number} not found")
    close = sql.find("*/", header.end())
    if close < 0:
        raise ValueError(f"section {number} header is not closed")
    body_start = close + 2
    following = _ANY_SECTION.search(sql, body_start)
    return sql[body_start: following.start() if following else len(sql)]


def bootstrap_sql(ddl: str) -> str:
    """The executable part of the bootstrap: everything before section 9.

    Section 9 is validation, run separately with `--expect-empty`; section 10
    onward is prose. The cut is made at the comment that holds the section 9
    header, so no comment is left open.
    """
    header = _section_header("9").search(ddl)
    if not header:
        return ddl
    opened = ddl.rfind("/*", 0, header.start())
    closed = ddl.rfind("*/", 0, header.start())
    return ddl[: opened if opened > closed else header.start()]


def rename_schemas(sql: str, *, gold: str = DEFAULT_GOLD, ops: str = DEFAULT_OPS) -> str:
    """Point the DDL at configured schema names. Identity when both are default."""
    if gold != DEFAULT_GOLD:
        sql = re.sub(rf"\b{DEFAULT_GOLD}\b", gold, sql)
    if ops != DEFAULT_OPS:
        sql = re.sub(rf"\b{DEFAULT_OPS}\b", ops, sql)
    return sql


# --------------------------------------------------------------------------
# The live-target guard
# --------------------------------------------------------------------------


class TargetMismatch(RuntimeError):
    """The Warehouse a script would touch is not the one it was allowed to."""


@dataclass(frozen=True)
class AllowedTarget:
    name: str
    workspace_id: str
    item_id: str
    #: Pinned endpoint. None for a deployed target, whose endpoint is whatever
    #: resolution returns (and must still equal the server we connect to).
    endpoint: str | None = None
    database: str | None = None
    bootstrap_approved: bool = False


@dataclass(frozen=True)
class ResolvedTarget:
    workspace_id: str
    item_id: str
    endpoint: str
    display_name: str


def _host(value: str | None) -> str:
    host = (value or "").strip().lower()
    host = re.sub(r"^tcp:", "", host)
    return host.split(",")[0].split(":")[0]


def check_target(
    allowed: AllowedTarget,
    resolved: ResolvedTarget,
    *,
    server: str,
    database: str,
) -> None:
    """Raise `TargetMismatch` unless every identity agrees. Executes nothing."""
    problems: list[str] = []
    if resolved.workspace_id.lower() != allowed.workspace_id.lower():
        problems.append(f"workspace {resolved.workspace_id} != allowed {allowed.workspace_id}")
    if resolved.item_id.lower() != allowed.item_id.lower():
        problems.append(f"item {resolved.item_id} != allowed {allowed.item_id}")
    if allowed.endpoint and _host(resolved.endpoint) != _host(allowed.endpoint):
        problems.append(f"endpoint {resolved.endpoint} != pinned {allowed.endpoint}")
    if _host(server) != _host(resolved.endpoint):
        problems.append(f"WAREHOUSE_SERVER {server!r} is not the resolved endpoint {resolved.endpoint}")
    expected_db = allowed.database or resolved.display_name
    if (database or "").strip() != expected_db:
        problems.append(f"WAREHOUSE_DATABASE {database!r} != {expected_db!r}")
    if problems:
        raise TargetMismatch(f"target '{allowed.name}' refused: " + "; ".join(problems))


def load_pinned_targets(path: Path) -> dict[str, AllowedTarget]:
    """Named, pinned targets from a JSON file. An absent file pins nothing."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: AllowedTarget(
            name=name,
            workspace_id=entry["workspace_id"],
            item_id=entry["item_id"],
            endpoint=entry.get("endpoint"),
            database=entry.get("database"),
            bootstrap_approved=bool(entry.get("bootstrap_approved", False)),
        )
        for name, entry in data.items()
        if not name.startswith("_")
    }


def resolve_via_fabric_api(
    workspace_id: str,
    item_id: str,
    *,
    get_json: Callable[[str], dict[str, Any]],
) -> ResolvedTarget:
    """Resolve a Warehouse item through the Fabric REST API.

    `get_json(url)` is injected so the guard is testable without a network.
    """
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/warehouses/{item_id}"
    body = get_json(url)
    endpoint = (body.get("properties") or {}).get("connectionString") or ""
    if not endpoint:
        raise TargetMismatch(f"Fabric API returned no SQL endpoint for item {item_id}")
    return ResolvedTarget(
        workspace_id=body.get("workspaceId") or workspace_id,
        item_id=body.get("id") or "",
        endpoint=endpoint,
        display_name=body.get("displayName") or "",
    )


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


@dataclass
class BatchResult:
    index: int
    label: str
    result_sets: list[list[tuple]] = field(default_factory=list)
    error: str | None = None

    @property
    def rows(self) -> int:
        return sum(len(rs) for rs in self.result_sets)


def run_batches(
    connection: Any,
    batches: Iterable[str],
    *,
    labels: Iterable[str] | None = None,
    stop_on_error: bool = True,
) -> list[BatchResult]:
    """Execute batches in order, collecting EVERY result set of each."""
    results: list[BatchResult] = []
    label_list = list(labels) if labels is not None else None
    for index, batch in enumerate(batches, start=1):
        label = label_list[index - 1] if label_list else statement_label(batch)
        result = BatchResult(index=index, label=label)
        cursor = connection.cursor()
        try:
            cursor.execute(batch)
            while True:
                if cursor.description:
                    result.result_sets.append([tuple(r) for r in cursor.fetchall()])
                if not cursor.nextset():
                    break
        except Exception as exc:  # noqa: BLE001 - reported per batch, then re-raised by the caller
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                pass
        results.append(result)
        if result.error and stop_on_error:
            break
    return results


# --------------------------------------------------------------------------
# Migrations
# --------------------------------------------------------------------------


class MigrationError(RuntimeError):
    """A migration set that cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sha256: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path) -> list[Migration]:
    """Every `NNNN_<slug>.sql` in version order. Version 0000 is the bootstrap's."""
    found: dict[str, Migration] = {}
    if not directory.exists():
        return []
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_FILE.match(path.name)
        if not match:
            raise MigrationError(f"{path.name}: migration files are named NNNN_<slug>.sql")
        version, name = match.groups()
        if version == BOOTSTRAP_VERSION:
            raise MigrationError(f"{path.name}: version 0000 is reserved for the bootstrap")
        if version in found:
            raise MigrationError(f"duplicate migration version {version}")
        text = path.read_text(encoding="utf-8")
        found[version] = Migration(version, name, path, sha256_text(text))
    return [found[v] for v in sorted(found)]


def pending_migrations(available: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """The migrations not yet recorded, refusing a recorded one whose file changed.

    A migration is immutable once applied: editing it would make the record lie
    about what ran. Write the next one instead.
    """
    for migration in available:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.sha256:
            raise MigrationError(
                f"migration {migration.version} was applied with sha256 {recorded[:12]}… "
                f"but the file now hashes to {migration.sha256[:12]}…; migrations are immutable"
            )
    return [m for m in available if m.version not in applied]


def table_exists(connection: Any, schema: str, table: str) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
            "WHERE s.name = ? AND t.name = ?",
            schema,
            table,
        )
        return int(cursor.fetchone()[0]) > 0
    finally:
        cursor.close()


def applied_migrations(connection: Any, ops: str) -> dict[str, str] | None:
    """{version: sha256} recorded in `<ops>.schema_migration`, or None if absent."""
    if not table_exists(connection, ops, "schema_migration"):
        return None
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT version, sha256 FROM {ops}.schema_migration")
        return {str(v).strip(): str(s).strip() for v, s in cursor.fetchall()}
    finally:
        cursor.close()


def apply_migration(connection: Any, migration: Migration, ops: str) -> list[BatchResult]:
    """Run one migration's batches, then record it. Not recorded if any batch fails."""
    text = migration.path.read_text(encoding="utf-8")
    results = run_batches(connection, split_batches(text))
    failed = [r for r in results if r.error]
    if failed:
        raise MigrationError(
            f"migration {migration.version} failed at batch {failed[0].index}: {failed[0].error}"
        )
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"INSERT INTO {ops}.schema_migration (version, name, sha256, applied_at, applied_by) "
            "VALUES (?, ?, ?, SYSUTCDATETIME(), SUSER_SNAME())",
            migration.version,
            migration.name,
            migration.sha256,
        )
    finally:
        cursor.close()
    if not getattr(connection, "autocommit", True):
        connection.commit()
    return results
