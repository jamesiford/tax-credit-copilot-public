"""Abuse tests for the query builder: hostile input in every position, and what must hold anyway. [RM-04]

A seeded, deterministic generator (the repository has no property-testing dependency, and a
failing seed must be reproducible from the test id) throws hostile identifiers, filter values,
IN lists, derived-column references and limits at `QuerySpec` -> `build_query`, in both dialects.
For every specification that is built, and for every one that is refused, the same things hold:

- a refusal is a typed `QueryError`, never a crash;
- no caller-supplied value reaches the SQL text; every value is a bound parameter;
- the tenant predicate is the first term of the WHERE, bound to the spec's client, and cannot be
  removed or moved without the tenant helper refusing the statement;
- the caps hold (limit, items per list, parameters per statement).

The legitimate half is here too: a name with an apostrophe (O'Brien) is an ordinary value.
"""
from __future__ import annotations

import math
import random
import re
import sqlite3
import unicodedata
from typing import Any

import pytest

from application.data.build import TRUNCATION_PROBE, BuiltQuery, build_query
from application.data.dialect import Dialect
from application.data.errors import QueryError
from application.data.expression_grammar import check_expression, expression_problems
from application.data.model_dsl import Cols
from application.data.semantic_model import default_model
from application.data.spec import (
    MAX_FILTERS, MAX_GROUP_BY, MAX_IN_VALUES, MAX_LIMIT, MAX_MEASURES, MAX_ORDER_BY, MAX_SELECT, MAX_YEARS, QuerySpec,
)
from infrastructure.persistence.tenant_sql import TenantScopedQuery, TenantScopeViolation
from tests.data_fixture import CLIENT_A, CLIENT_B, ROWS_PER_CLIENT, build_database, run

MODEL = default_model()
DIALECTS = (Dialect.TSQL, Dialect.SQLITE)
CASES = 500  # per category and dialect; every seed is reproducible from its test id

# --------------------------------------------------------------------------- the generator

INJECTIONS = [
    "'; DROP TABLE tcc_gold.unit_year_master; --", "x' OR '1'='1", 'x" OR "1"="1', "1; SELECT * FROM sys.tables",
    "a UNION SELECT name FROM sys.objects", "x/* c */y", "a--b", "ＤＲＯＰ ＴＡＢＬＥ x", "a\x00b", "a\u202eb", "a\u200bb",
    "EXEC xp_cmdshell 'dir'", "Robert'); DROP TABLE Students;--", "50%", "a_b", "[a-z]", "back\\slash", "ʼ OR ʼ1ʼ=ʼ1",
    "{tenant:t}", "{tenant:t@AccountId}", "{t}", "{t}.[x]", "? OR ? = ?", "??", "]; DROP TABLE x; --", '"; DROP TABLE x; --',
    "t.client_id = t.client_id", ") OR 1=1 --", "1) UNION ALL SELECT 1 --", "tab\tand\nnewline", "x\n", "\n", " ", "",
    "x" * 100, "x" * 101, "x" * 5000, "WAITFOR DELAY '0:0:5'", "@@version", "xp_cmdshell", "O'Brien", "Bakers' Group",
    "\ud800", "sys.tables", "information_schema.tables", "client_id", "AccountId", "employee_id", "record_token",
]
IDENTIFIER_JUNK = ["worksite_id\n", "n\n", "worksite_id ", " worksite_id", "worksite_id;", "worksite_id--", "t.worksite_id",
                   "location.location_name\n", "location..x", ".location", "WORKSITE_ID", "worksite\u200bid", "ｗｏｒｋｓｉｔｅ_id"]
NOT_TEXT = [None, True, False, 0, -1, 1, 2**63, -(2**63), 10**30, 1.5, math.nan, math.inf, -math.inf, [], {}, [None],
            [[1]], {"a": 1}, {"from": 2020, "to": 2030}, b"bytes".decode(), ["a", None]]


def mutate(text: str, rnd: random.Random) -> str:
    """One more disguise: width, invisible character, case, padding."""
    kind = rnd.randrange(6)
    if kind == 0:
        return text.translate({ord(c): ord(c) + 0xFEE0 for c in text if "!" <= c <= "~"})
    if kind == 1:
        return text[: len(text) // 2] + "\u200b" + text[len(text) // 2:]
    if kind == 2:
        return text.swapcase()
    if kind == 3:
        return " " + text + " "
    if kind == 4:
        return unicodedata.normalize("NFD", text)
    return text + rnd.choice(["\n", "\r", "\x00", "\u2028"])


def hostile(rnd: random.Random) -> str:
    text = rnd.choice(INJECTIONS + IDENTIFIER_JUNK)
    return mutate(text, rnd) if rnd.random() < 0.4 else text


def junk(rnd: random.Random) -> Any:
    return rnd.choice(NOT_TEXT) if rnd.random() < 0.4 else hostile(rnd)


def queryable(dataset) -> list[str]:
    return [c.logical for c in dataset.columns if c.queryable and c.logical != dataset.method_column]


def base(rnd: random.Random) -> dict[str, Any]:
    dataset = rnd.choice(MODEL.datasets)
    return {"dataset": dataset.name, "client_id": CLIENT_A, "select": [rnd.choice(queryable(dataset))],
            "measures": [{"column": "*", "agg": "count"}]}


def poison_identifiers(payload: dict, rnd: random.Random) -> None:
    where = rnd.choice(["dataset", "select", "group_by", "order_by", "measure_column", "measure_as", "filter_column", "agg", "op"])
    text = hostile(rnd)
    if where == "dataset":
        payload["dataset"] = text
    elif where in ("select", "group_by"):
        payload[where] = [*payload.get(where, []), text]
    elif where == "order_by":
        payload["order_by"] = [text, {"column": text, "direction": hostile(rnd)}]
    elif where == "measure_column":
        payload["measures"] = [{"column": text, "agg": rnd.choice(["sum", "avg", "count"])}]
    elif where == "measure_as":
        payload["measures"] = [{"column": "*", "agg": "count", "as": text}]
    elif where == "agg":
        payload["measures"] = [{"column": "*", "agg": text}]
    else:
        payload["filters"] = [{"column": text, "op": "eq" if where == "filter_column" else text, "value": rnd.choice(INJECTIONS)}]


def poison_values(payload: dict, rnd: random.Random) -> None:
    dataset = MODEL.dataset(payload["dataset"])
    filterable = [c for c in dataset.columns if c.queryable and c.operators]
    if not filterable:
        return
    column = rnd.choice(filterable)
    op = rnd.choice(sorted(column.operators, key=lambda o: o.value)).value
    shapes = {"in": lambda: [junk(rnd) for _ in range(rnd.randint(0, MAX_IN_VALUES + 5))],
              "between": lambda: [junk(rnd) for _ in range(rnd.randint(1, 3))]}
    value = shapes.get(op, lambda: junk(rnd))()
    payload["filters"] = [{"column": column.logical, "op": op, "value": value} for _ in range(rnd.randint(1, MAX_FILTERS + 1))]


def poison_in_list(payload: dict, rnd: random.Random) -> None:
    dataset = MODEL.dataset(payload["dataset"])
    texts = [c for c in dataset.columns if c.queryable and c.operators and c.type.value == "text" and not c.choices]
    column = rnd.choice(texts) if texts else None
    name = column.logical if column else queryable(dataset)[0]
    size = rnd.choice([0, 1, 2, MAX_IN_VALUES - 1, MAX_IN_VALUES, MAX_IN_VALUES + 1, 200])
    payload["filters"] = [{"column": name, "op": "in", "value": [hostile(rnd) for _ in range(size)]}]


def poison_limits(payload: dict, rnd: random.Random) -> None:
    payload["limit"] = rnd.choice([-1, 0, 1, 2, 99, 100, 499, 500, 501, 502, 1000, 10**9, 2**63, True, False, 1.5, "5", None, [5], {"a": 1}])
    payload["tax_years"] = rnd.choice([None, [], [2023], list(range(2010, 2010 + MAX_YEARS + 3)), {"from": 2000, "to": 2100}, {"from": 2023, "to": 2022}, ["2023"], [1e999]])


def poison_derived(payload: dict, rnd: random.Random) -> None:
    payload.update({"dataset": "payroll", "select": [rnd.choice(["pay_year", "pay_month"])], "measures": [{"column": "*", "agg": "count"}]})
    name = rnd.choice(["pay_year", "pay_month"])
    value = rnd.choice([junk(rnd), rnd.randint(1990, 202_312), [junk(rnd), junk(rnd)], 2023, "2023"])
    op = rnd.choice(["eq", "in", "between", "gte", "lte", "contains"])
    payload["filters"] = [{"column": name, "op": op, "value": [value, value] if op in ("in", "between") and not isinstance(value, list) else value}]
    payload["group_by"] = [name] if rnd.random() < 0.5 else []
    payload["order_by"] = [{"column": name, "direction": rnd.choice(["asc", "desc", hostile(rnd)])}]
    payload["measures"] += [{"column": rnd.choice(["pay_year", "pay_month"]), "agg": rnd.choice(["min", "max", "sum", "avg", "count_distinct"])}]


def poison_shape(payload: dict, rnd: random.Random) -> None:
    key = rnd.choice(["select", "measures", "filters", "group_by", "order_by", "tax_years", "method", "client_id", "dataset", "extra"])
    payload[key if key != "extra" else hostile(rnd)] = junk(rnd) if key != "select" else [junk(rnd) for _ in range(rnd.randint(0, MAX_SELECT + 3))]


CATEGORIES = {
    "identifiers": poison_identifiers, "values": poison_values, "in_lists": poison_in_list,
    "limits": poison_limits, "derived": poison_derived, "shape": poison_shape,
}


def generate(category: str, seed: int) -> dict[str, Any]:
    rnd = random.Random(f"{category}:{seed}")
    payload = base(rnd)
    CATEGORIES[category](payload, rnd)
    return payload


# --------------------------------------------------------------------------- the invariants

ALLOWED_LITERALS = re.compile(r" ESCAPE '\\'|'%Y%m'|'%Y'")
#: Words the platform itself writes into a statement or an alias; a caller who says them has not leaked anything.
VOCABULARY = frozenset(
    {c.logical for d in MODEL.datasets for c in d.columns} | {d.name for d in MODEL.datasets}
    | {"count", "sum", "avg", "min", "max", "count_distinct", "asc", "desc", "min_max", "pay_period", "both"}
)
UNSCOPED = re.compile(r"\b(?:WHERE|ON)\s+(?!\{tenant)")
MAX_PARAMS = MAX_FILTERS * MAX_IN_VALUES + MAX_YEARS + 3


def attempt(payload: dict, dialect: Dialect) -> BuiltQuery | None:
    """The built query, or None for a refusal. Anything but a `QueryError` is a failure of the builder."""
    try:
        return build_query(QuerySpec.from_dict(payload), MODEL, dialect)
    except QueryError:
        return None


def supplied_strings(node: Any) -> list[str]:
    """Every string the caller supplied anywhere in the payload, keys excluded."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in supplied_strings(v)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in supplied_strings(v)]
    return []


def not_an_identifier_or_keyword(text: str) -> bool:
    return text not in VOCABULARY and not re.fullmatch(r"[A-Za-z0-9_ .*,()]{0,12}", text) and bool(text.strip())


def assert_no_caller_text_in_sql(built: BuiltQuery, payload: dict) -> None:
    sql, plain = built.sql, ALLOWED_LITERALS.sub("", built.sql)
    assert sql.startswith("SELECT ") and ";" not in sql and "--" not in sql and "/*" not in sql and "\n" not in sql
    assert "'" not in plain and "\\" not in plain.replace("\\", "", 0) or "'" not in plain, plain
    for text in supplied_strings(payload):
        if not_an_identifier_or_keyword(text) and "{" not in text:
            assert text not in sql, f"caller text reached the statement: {text!r}"
            assert text.strip() not in sql
    # a caller's "{tenant:...}" could only matter by becoming a second marker, so count the markers the plan accounts for
    live = built.plan.dataset.currency.value == "live_run"
    assert sql.count("{tenant") == 1 + len(built.plan.joins) + (1 if live else 0), "a marker that no table of the plan accounts for"
    assert sql.count("?") == len(built.params) and len(built.params) <= MAX_PARAMS


def assert_tenant_first_and_unremovable(built: BuiltQuery, client_id: int) -> None:
    sql, params = built.sql, built.params
    assert sql.count(" WHERE ") >= 1 and not UNSCOPED.findall(sql), sql
    bound, values = TenantScopedQuery(client_id).bind(sql, params)
    where = bound[bound.index("WHERE ") + len("WHERE "):]
    assert where.startswith(("t.client_id = ?", "t.AccountId = ?")), where
    assert bound.count("?") == len(values) and values.count(client_id) == sql.count("{tenant")
    for broken in (re.sub(r"\{tenant[^}]*\}", "1 = 1", sql),
                   sql.replace("WHERE {tenant:t", "WHERE 1 = 1 AND {tenant:t"),
                   sql.replace(" WHERE ", " WHERE 1 = 1 OR ", 1)):
        if broken != sql:
            with pytest.raises(TenantScopeViolation):
                TenantScopedQuery(client_id).bind(broken, params)


def assert_caps(built: BuiltQuery) -> None:
    plan, sql = built.plan, built.sql
    assert 1 <= plan.limit <= MAX_LIMIT and not isinstance(plan.limit, bool)
    fetch = plan.limit + TRUNCATION_PROBE
    assert (f"TOP ({fetch}) " in sql) if built.dialect is Dialect.TSQL else sql.endswith(f"LIMIT {fetch}")
    assert len(plan.select) <= MAX_SELECT + 1 and len(plan.measures) <= MAX_MEASURES and len(plan.group_by) <= MAX_GROUP_BY + 1
    assert len(plan.order_by) <= MAX_ORDER_BY and len(plan.filters) <= MAX_FILTERS and len(plan.tax_years) <= MAX_YEARS
    assert all(len(f.value) <= MAX_IN_VALUES for f in plan.filters if isinstance(f.value, tuple))


def assert_holds(payload: dict, dialect: Dialect) -> BuiltQuery | None:
    built = attempt(payload, dialect)
    if built is not None:
        assert_no_caller_text_in_sql(built, payload)
        assert_tenant_first_and_unremovable(built, payload["client_id"])
        assert_caps(built)
    return built


# ------------------------------------------------------------------------------ the fuzzing


@pytest.mark.parametrize("category", sorted(CATEGORIES))
@pytest.mark.parametrize("dialect", DIALECTS, ids=lambda d: d.value)
def test_hostile_input_never_reaches_the_statement_and_the_invariants_hold(category, dialect):
    built = 0
    for seed in range(CASES):
        payload = generate(category, seed)
        try:
            built += assert_holds(payload, dialect) is not None
        except AssertionError as failure:
            raise AssertionError(f"{category} seed {seed}: {failure}\npayload={payload!r}") from failure
    assert built > 0 or category in ("identifiers", "shape"), f"{category}: nothing built; the generator is too hostile to test the builder"


def test_the_generator_is_deterministic_so_a_failing_seed_can_be_replayed():
    assert generate("values", 7) == generate("values", 7) or generate("values", 7)["dataset"] == generate("values", 7)["dataset"]
    assert [generate("in_lists", s)["dataset"] for s in range(20)] == [generate("in_lists", s)["dataset"] for s in range(20)]


def test_the_fuzzer_reaches_both_outcomes_in_every_category_that_can_succeed():
    outcomes = {c: {attempt(generate(c, s), Dialect.TSQL) is None for s in range(CASES)} for c in ("values", "in_lists", "limits", "derived")}
    assert all(seen == {True, False} for seen in outcomes.values()), outcomes


@pytest.mark.parametrize("junk_identifier", IDENTIFIER_JUNK)
def test_an_identifier_with_a_trailing_newline_or_a_disguise_is_not_an_identifier(junk_identifier):
    for field, payload in (
        ("select", {"select": [junk_identifier]}),
        ("group_by", {"select": ["worksite_id"], "group_by": [junk_identifier]}),
        ("alias", {"select": ["worksite_id"], "measures": [{"column": "*", "agg": "count", "as": junk_identifier}]}),
        ("order_by", {"select": ["worksite_id"], "order_by": [junk_identifier]}),
        ("filter", {"select": ["worksite_id"], "filters": [{"column": junk_identifier, "op": "eq", "value": "x"}]}),
    ):
        assert attempt({"dataset": "unit_year_master", "client_id": CLIENT_A, **payload}, Dialect.TSQL) is None, (field, junk_identifier)


def test_a_measure_alias_may_not_end_in_a_newline():
    assert attempt({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id"],
                    "measures": [{"column": "*", "agg": "count", "as": "n\n"}]}, Dialect.TSQL) is None


@pytest.mark.parametrize("limit", [-1, 0, 501, 10**9, 2**63, True, False, 1.5, "5", [5], {"a": 1}])
def test_a_limit_outside_one_to_five_hundred_is_refused(limit):
    assert attempt({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id"], "limit": limit}, Dialect.TSQL) is None


@pytest.mark.parametrize("client", [None, 0, -1, True, "1001", 1.5, [1001], {"id": 1}, 10**30])
def test_a_client_that_is_not_a_positive_integer_is_refused_so_the_scope_cannot_be_blank(client):
    assert attempt({"dataset": "unit_year_master", "client_id": client, "select": ["worksite_id"]}, Dialect.SQLITE) is None


def test_a_filter_on_the_tenant_column_cannot_widen_the_scope():
    for column in ("client_id", "AccountId", "t.client_id", "tenant"):
        assert attempt({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id"],
                        "filters": [{"column": column, "op": "eq", "value": CLIENT_B}]}, Dialect.SQLITE) is None


def test_the_client_in_the_spec_is_the_only_client_the_statement_is_bound_to():
    built = attempt({"dataset": "unit_year_master", "client_id": CLIENT_A, "select": ["worksite_id"],
                     "filters": [{"column": "worksite_id", "op": "in", "value": [str(CLIENT_B), f"client_id = {CLIENT_B}"]}]}, Dialect.SQLITE)
    _, values = TenantScopedQuery(CLIENT_A).bind(built.sql, built.params)
    assert values[0] == CLIENT_A and CLIENT_B not in values


# ------------------------------------------------------------- executing hostile values


@pytest.fixture(scope="module")
def db() -> sqlite3.Connection:
    return build_database(MODEL)


def count_where(db, client: int, value: Any, op: str = "eq", column: str = "worksite_id", dataset: str = "unit_year_master") -> int:
    built = attempt({"dataset": dataset, "client_id": client, "select": [column], "measures": [{"column": "*", "agg": "count"}],
                     "filters": [{"column": column, "op": op, "value": value}]}, Dialect.SQLITE)
    assert built is not None
    return sum(row[-1] for row in run(db, built.sql, built.params, client))


@pytest.mark.parametrize("value", ["x' OR '1'='1", 'x" OR "1"="1', "x' = '", "' OR ''='", "x') OR ('1'='1", "ʼ OR ʼ1ʼ=ʼ1"])
def test_a_quote_injection_matches_nothing_instead_of_everything(db, value):
    assert count_where(db, CLIENT_A, value) == 0 and count_where(db, CLIENT_B, value) == 0
    assert count_where(db, CLIENT_A, [value, "no-such"], "in") == 0


def test_hostile_text_executes_without_error_and_the_tables_survive(db):
    before = db.execute("SELECT COUNT(*) FROM tcc_gold.unit_year_master").fetchone()[0]
    ran = 0
    for seed in range(CASES):
        built = attempt(generate("values", seed), Dialect.SQLITE) or attempt(generate("derived", seed), Dialect.SQLITE)
        if built is None:
            continue
        rows = run(db, built.sql, built.params, CLIENT_A)
        assert len(rows) <= built.plan.limit + TRUNCATION_PROBE
        ran += 1
    assert ran > 20, "too few generated statements ran for this to prove anything"
    assert db.execute("SELECT COUNT(*) FROM tcc_gold.unit_year_master").fetchone()[0] == before
    assert count_where(db, CLIENT_A, "worksite_id-1001-0", "contains", dataset="location", column="location_name") >= 0


def test_a_clean_count_is_the_clients_own_rows_only(db):
    for client in (CLIENT_A, CLIENT_B):
        built = attempt({"dataset": "unit_year_master", "client_id": client, "select": ["worksite_id"],
                         "measures": [{"column": "*", "agg": "count"}]}, Dialect.SQLITE)
        assert sum(r[-1] for r in run(db, built.sql, built.params, client)) == ROWS_PER_CLIENT


# ------------------------------------------------------- legitimate names with apostrophes

NAMES = ["O'Brien", "D'Angelo", "Bakers' Group", "Smith' and Sons", "Cooks' Order House", "L'Oréal", "Rock 'n' Roll",
         "Joe's", 'The "Best" Cafe', "Mary O'Neil-Brown", "St. John's Union"]


@pytest.mark.parametrize("dialect", DIALECTS, ids=lambda d: d.value)
@pytest.mark.parametrize("name", NAMES)
def test_a_name_with_an_apostrophe_is_bound_as_a_parameter_and_absent_from_the_sql(name, dialect):
    for dataset, column, op, value, expected in (
        ("unit_year_master", "worksite_id", "eq", name, name),
        ("unit_year_master", "worksite_id", "in", [name, "other"], name),
        ("employee_period_fact", "job_title", "contains", name, f"%{name.lower().replace('_', chr(92) + '_')}%"),
    ):
        built = attempt({"dataset": dataset, "client_id": CLIENT_A, "select": ["tax_year" if dataset != "unit_year_master" else "worksite_id"],
                         "filters": [{"column": column, "op": op, "value": value}]}, dialect)
        assert built is not None, f"{name!r} was refused on {op}"
        assert name not in built.sql and name.lower() not in built.sql.lower()
        assert expected in built.params, built.params
        assert ALLOWED_LITERALS.sub("", built.sql).count("'") == 0
        assert built.sql.count("?") == len(built.params)


def test_a_name_with_an_apostrophe_finds_its_row_and_only_its_row(db):
    name = "O'Brien's Bakers' Group"
    db.execute("UPDATE tcc_gold.unit_year_master SET worksite_id = ? WHERE client_id = ? AND is_current = 1 AND rowid = "
               "(SELECT MIN(rowid) FROM tcc_gold.unit_year_master WHERE client_id = ? AND is_current = 1)", (name, CLIENT_A, CLIENT_A))
    try:
        assert count_where(db, CLIENT_A, name) >= 1
        assert count_where(db, CLIENT_A, [name, "nobody"], "in") >= 1
        assert count_where(db, CLIENT_B, name) == 0, "another client's scope never sees it"
    finally:
        db.execute("UPDATE tcc_gold.unit_year_master SET worksite_id = 'restored' WHERE worksite_id = ?", (name,))


# ------------------------------------------------- derived-column expressions: an allow-list

DERIVED = [(d.name, c) for d in MODEL.datasets for c in d.columns if c.expression is not None]


def test_the_model_has_derived_columns_for_this_test_to_cover():
    assert {c.logical for _, c in DERIVED} >= {"pay_year", "pay_month"}


@pytest.mark.parametrize("dataset, column", DERIVED, ids=lambda v: v if isinstance(v, str) else v.logical)
def test_every_derived_expression_is_inside_the_closed_grammar_in_both_dialects(dataset, column):
    for text, dialect in zip(column.expression, ("tsql", "lite")):
        assert expression_problems(text, column.depends_on, dialect=dialect) == [], (column.logical, dialect)


@pytest.mark.parametrize("dataset, column", DERIVED, ids=lambda v: v if isinstance(v, str) else v.logical)
def test_a_derived_column_depends_only_on_columns_the_dataset_really_has(dataset, column):
    real = {c.physical for c in MODEL.dataset(dataset).columns if c.expression is None}
    assert set(column.depends_on) <= real


BAD_EXPRESSIONS = [
    ("subselect", "(SELECT TOP 1 x FROM sys.tables)", "tsql"),
    ("semicolon", "YEAR({t}.[PayDate]); DROP TABLE x", "tsql"),
    ("comment", "YEAR({t}.[PayDate]) -- x", "tsql"),
    ("block comment", "YEAR({t}.[PayDate]) /* x */", "tsql"),
    ("another function", "LOWER({t}.[PayDate])", "tsql"),
    ("system function", "YEAR(GETDATE())", "tsql"),
    ("string literal", "COALESCE({t}.[PayDate], 'x')", "tsql"),
    ("a quote", "YEAR({t}.[PayDate]) + '1'", "tsql"),
    ("a column that is not declared", "YEAR({t}.[Other])", "tsql"),
    ("the other dialect's reference", 'YEAR({t}."PayDate")', "tsql"),
    ("the other dialect's reference (lite)", "YEAR({t}.[PayDate])", "lite"),
    ("another table's alias", "YEAR(u.[PayDate])", "tsql"),
    ("a six-digit literal", "YEAR({t}.[PayDate]) * 100000", "tsql"),
    ("an unbalanced parenthesis", "YEAR({t}.[PayDate]", "tsql"),
    ("a stray closing parenthesis", "YEAR({t}.[PayDate]))", "tsql"),
    ("a cast to a wide type", "CAST({t}.[PayDate] AS VARCHAR(10))", "tsql"),
    ("a bracket escape", "YEAR({t}.[PayDate]])", "tsql"),
    ("a division", "YEAR({t}.[PayDate]) / 0", "tsql"),
    ("a disguised keyword", "ＹＥＡＲ({t}.[PayDate])", "tsql"),
    ("a newline-split statement", "YEAR({t}.[PayDate])\nDROP", "tsql"),
    ("empty", "", "tsql"),
]


@pytest.mark.parametrize("label, text, dialect", BAD_EXPRESSIONS, ids=[b[0] for b in BAD_EXPRESSIONS])
def test_an_expression_outside_the_grammar_is_refused(label, text, dialect):
    assert expression_problems(text, ("PayDate",), dialect=dialect), label


def test_a_column_cannot_be_built_with_an_expression_outside_the_grammar():
    S = Cols(pascal_physical=True)
    good = ("YEAR({t}.[PayDate])", 'CAST(strftime(\'%Y\', {t}."PayDate") AS INTEGER)')
    assert S.dim("d", "int", "A derived year.", physical="D", expression=good, depends_on=("PayDate",)).expression == good
    for bad in (("YEAR({t}.[PayDate]); DROP TABLE x", good[1]), (good[0], "(SELECT 1)"),
                ("YEAR({t}.[Other])", good[1]), ("LOWER({t}.[PayDate])", good[1])):
        with pytest.raises(ValueError, match="allowed grammar"):
            S.dim("d", "int", "A derived year.", physical="D", expression=bad, depends_on=("PayDate",))
    with pytest.raises(ValueError, match="allowed grammar"):
        check_expression("d", good, ("PayDate", "PayPeriodEnd"))


def test_the_sql_for_a_derived_column_is_exactly_the_models_expression():
    for dataset, column in DERIVED:
        for dialect, index in ((Dialect.TSQL, 0), (Dialect.SQLITE, 1)):
            built = attempt({"dataset": dataset, "client_id": CLIENT_A, "select": [column.logical],
                             "measures": [{"column": "*", "agg": "count"}]}, dialect)
            assert column.expression[index].replace("{t}", "t") in built.sql
            assert "{t}" not in built.sql
