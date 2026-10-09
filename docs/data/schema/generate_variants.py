"""Generate the SQL Server variant of the Tax Credit Copilot schema from the Fabric one.

    python docs/data/schema/generate_variants.py

`tcc-schema.fabric.sql` is the source of truth. It is written to the Fabric
Warehouse T-SQL subset, which is what makes both targets reachable from one
file: Fabric's subset is valid SQL Server, so the translation only ever ADDS.

Two mechanical edits, both verified against SQL Server 2025:

  1. Strip ``NOT ENFORCED``. It is Fabric/Synapse syntax; SQL Server rejects it
     with "'NOT ENFORCED' is not supported in this version of SQL Server".
     Removing it turns 11 advisory keys into enforced ones.

  2. Emit the indexes. Fabric rejects ``CREATE INDEX`` outright, so the access
     patterns live in the section 1a table as documentation. On SQL Server they
     become real indexes, generated from that same table so the two cannot
     disagree.

Not automated, deliberately: the CONSTRAINT INTENT blocks describe CHECK
constraints and filtered unique indexes that SQL Server supports and Fabric does
not. Promoting them is a judgement call about what to enforce versus what to
validate, so it stays a human decision rather than a regex.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "tcc-schema.fabric.sql"
TARGET = HERE / "tcc-schema.sqlserver.sql"

BANNER = """/* ============================================================================
   GENERATED FILE — DO NOT EDIT

   Produced from tcc-schema.fabric.sql by generate_variants.py.
   Hand-edits are lost on the next run and silently desynchronise the two
   platforms. Change the Fabric file and regenerate.

   Differences from the Fabric source, and only these:
     - NOT ENFORCED removed, so every primary key is genuinely enforced
     - the section 1a access patterns emitted as real CREATE INDEX statements

   Still worth doing by hand on this target, because SQL Server supports what
   Fabric does not: promote the CONSTRAINT INTENT blocks to real CHECK
   constraints, and make the "one current row" uniqueness a filtered unique
   index. On Fabric those are validation queries; here they can be constraints.
   ============================================================================ */

"""


def access_patterns(sql: str) -> list[tuple[str, str]]:
    """Read section 1a's table, stitching rows whose column list wrapped.

    Returns (table, columns) in file order. A wrapped row has an empty left
    cell and the tail of the previous column list on the right.
    """
    section = re.search(r"1a\. ACCESS PATTERNS(.*?)-{20,}\s*\*/", sql, re.S)
    if not section:
        sys.exit("could not find the section 1a access-pattern table")

    out: list[tuple[str, str]] = []
    carry: tuple[str, str] | None = None
    for line in section.group(1).splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) != 2:
            continue
        left, right = cells
        if left == "Table" or set(left) <= set("-") or (not left and not right):
            continue
        if not left and right and carry:
            carry = (carry[0], f"{carry[1]} {right}".strip())
            continue
        if carry:
            out.append(carry)
        carry = (left, right)
    if carry:
        out.append(carry)
    return [(t, c.rstrip(",").strip()) for t, c in out if re.match(r"^[a-z_]+$", t)]


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"missing source: {SOURCE}")
    sql = SOURCE.read_text(encoding="utf-8")

    # map bare table name -> schema-qualified name, from the CREATE statements
    qualified = {
        name.split(".")[1]: name
        for name in re.findall(r"(?m)^CREATE TABLE\s+(\S+)", sql)
    }

    # 1. NOT ENFORCED is Fabric-only. Strip it from executable SQL ONLY —
    #    the comment blocks explain the Fabric/SQL Server difference and must
    #    keep saying "NOT ENFORCED" or the explanation stops making sense.
    n_enforced = 0
    pieces: list[str] = []
    cursor = 0
    for block in re.finditer(r"/\*.*?\*/", sql, re.S):
        code = sql[cursor:block.start()]
        code, n = re.subn(r"\s+NOT ENFORCED", "", code)
        n_enforced += n
        pieces.append(code)
        pieces.append(block.group(0))          # comment passes through untouched
        cursor = block.end()
    tail, n = re.subn(r"\s+NOT ENFORCED", "", sql[cursor:])
    n_enforced += n
    pieces.append(tail)
    out = "".join(pieces)

    # 2. Rebuild the indexes from the documented access patterns.
    patterns = access_patterns(sql)
    seen: dict[str, int] = {}
    statements: list[str] = []
    for table, cols in patterns:
        if table not in qualified:
            print(f"  skipped (no such table): {table}")
            continue
        cols = " ".join(cols.split())
        seen[table] = seen.get(table, 0) + 1
        suffix = "" if seen[table] == 1 else f"_{seen[table]}"
        statements.append(
            f"CREATE INDEX ix_{table}{suffix}\n"
            f"    ON {qualified[table]} ({cols});\nGO"
        )

    index_block = (
        "\n\n/* ----------------------------------------------------------------------------\n"
        "   INDEXES\n\n"
        "   Generated from the section 1a access patterns. Fabric Warehouse rejects\n"
        "   CREATE INDEX, so on that platform these exist only as documentation; here\n"
        "   they are real. Both come from the same table, so they cannot disagree.\n"
        "   ---------------------------------------------------------------------------- */\n\n"
        + "\n\n".join(statements)
        + "\n"
    )

    # place the indexes after the last DDL statement, before the validation section
    marker = re.search(r"(?m)^/\* =+\s*\n\s*9\.", out)
    if marker:
        out = out[: marker.start()] + index_block + "\n\n" + out[marker.start():]
    else:
        out += index_block

    out = out.replace(
        "Target: Microsoft Fabric  (Warehouse T-SQL, or Fabric SQL Database)",
        "Target: Microsoft SQL Server 2016 or later  (GENERATED — see banner)",
    )
    TARGET.write_text(BANNER + out, encoding="utf-8")

    print(f"source : {SOURCE.name}")
    print(f"target : {TARGET.name}")
    print(f"  NOT ENFORCED removed : {n_enforced}")
    print(f"  indexes generated    : {len(statements)}")


if __name__ == "__main__":
    main()
