"""Hermetic source evidence only: no service, credentials, Delta read, or product mutation."""
import gzip
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

assert sys.version_info[:2] == (3, 12), "Only CPython 3.12 is the source oracle"
root = Path.cwd()
import domain

assert Path(domain.__file__).resolve().is_relative_to(root / "backend")
from data.source import from_fabric, mapping
from data.source.schema import SourceDataset
from data.source.to_delta import TABLE_SPECS
from data.source.to_bcs import source_to_bcs_rows, projection_controls
from data.lookups import store

store.install(None)
mode = sys.argv[1]
request = json.load(sys.stdin)
if mode == "sql":
    # Executes the actual generated statement, not the materialized transport's
    # semantic plan. SQLite is an offline SQL cross-check, not a T-SQL attestation.
    import sqlite3

    with sqlite3.connect(":memory:") as connection:
        schema = request["schema"]
        quote = lambda name: '"' + name.replace('"', '""') + '"'
        connection.execute("ATTACH DATABASE ':memory:' AS " + quote(schema))
        connection.create_function("YEAR", 1, lambda value: int(value[:4]) if value else None)
        for table, columns in request["columns"].items():
            qualified = quote(schema) + "." + quote(table)
            connection.execute("CREATE TABLE " + qualified + " (" + ",".join(map(quote, columns)) + ")")
            statement = "INSERT INTO " + qualified + " VALUES (" + ",".join("?" for _ in columns) + ")"
            connection.executemany(statement, ([row.get(c) for c in columns] for row in request["tables"][table]))
        sql = request["sql"].replace("COUNT_BIG(", "COUNT(")
        parameters = {f"p{i}": value for i, value in enumerate(request["parameters"])}
        print(json.dumps(connection.execute(sql, parameters).fetchall(), separators=(",", ":")))
    sys.exit(0)
if mode == "p2":
    tables = {}
    for path in (root / "contract" / "seed" / "P2" / "source").glob("*.jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as source:
            tables[path.name.split(".")[0]] = [json.loads(line) for line in source]
else:
    tables = request["tables"]

def build(account):
    records = {}
    for table, physical in tables.items():
        fields = mapping.table_map(table).fields
        rows = [{key: row.get(field.column) for key, field in fields.items()} for row in physical]
        tenant = mapping.table_map(table).tenant_field
        if tenant:
            rows = [row for row in rows if row.get(tenant) == account]
        for row in rows:
            for key, field in fields.items():
                if field.type == "date32" and isinstance(row[key], str):
                    try:
                        row[key] = date.fromisoformat(row[key][:10])
                    except ValueError:
                        row[key] = None
        records[table] = from_fabric._rows_to(from_fabric._CLASS_FOR[table], rows, TABLE_SPECS[table][1])
    dataset = SourceDataset(account=records["Account"][0])
    for table, rows in records.items():
        attr = mapping.table_map(table).dataset_attr
        if attr != "account":
            setattr(dataset, attr, rows)
    return dataset

from tests.certified_synthetic import certified_synthetic_pack
from domain.calculation.onezero import run_min_max_method, run_pay_period_method

output = []
for account in request["accounts"]:
    dataset = build(account)
    rows = source_to_bcs_rows(dataset)
    result = {
        "account": account,
        "rows": len(rows),
        "hash": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "controls": projection_controls(dataset, rows),
    }
    if mode != "p2":
        result["projected"] = rows
    selected = [row for row in rows if row["Tax_Year"] == 2024 and row["Work_State"] == "GA"]
    common = dict(tax_year=2024, analysis_start_month=date(2024, 1, 1), pack=certified_synthetic_pack(),
                  fiscal_window=(date(2024, 1, 1), date(2024, 12, 31)))
    result["methods"] = []
    for method in (run_min_max_method, run_pay_period_method):
        answer = method(selected, **common)
        result["methods"].append([answer.annual_average, sorted(row["Employee_ID"] for row in answer.eligible_employees)])
    output.append(result)
print(json.dumps(output, separators=(",", ":")))
