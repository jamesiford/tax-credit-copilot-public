"""The tenant marker may name a table's client column, from a closed set. [CH-16b]

The lakehouse source tables key on `AccountId`, not `client_id`. The marker gains an
optional `@Column`; everything else about the helper (first term of WHERE/ON, bound value,
refusal without a marker) is untouched, and the existing tenant tests still pass unedited.
"""
from __future__ import annotations

import pytest

from infrastructure.persistence.tenant_sql import TENANT_COLUMNS, TenantScopedQuery, TenantScopeViolation


def test_a_marker_without_a_column_still_means_client_id():
    sql, params = TenantScopedQuery(7).bind("SELECT 1 FROM t WHERE {tenant} AND x = ?", [3])
    assert sql == "SELECT 1 FROM t WHERE client_id = ? AND x = ?"
    assert params == [7, 3]


def test_a_marker_can_name_account_id_with_and_without_an_alias():
    sql, params = TenantScopedQuery(7).bind("SELECT 1 FROM T AS p WHERE {tenant:p@AccountId} AND x = ?", [3])
    assert sql == "SELECT 1 FROM T AS p WHERE p.AccountId = ? AND x = ?"
    assert params == [7, 3]
    sql, _ = TenantScopedQuery(7).bind("SELECT 1 FROM T WHERE {tenant@AccountId}")
    assert sql.endswith("WHERE AccountId = ?")


def test_a_join_marker_and_a_where_marker_each_bind_the_client_in_text_order():
    sql, params = TenantScopedQuery(7).bind(
        "SELECT 1 FROM T AS p LEFT JOIN L AS l ON {tenant:l@AccountId} AND p.a = l.a WHERE {tenant:p@AccountId} AND p.b = ?",
        ["v"],
    )
    assert sql.count("AccountId = ?") == 2
    assert params == [7, 7, "v"]


@pytest.mark.parametrize("column", ["password", "ClientId", "client_id; DROP TABLE t", "x"])
def test_a_column_outside_the_closed_set_is_refused(column):
    with pytest.raises(TenantScopeViolation):
        TenantScopedQuery(7).bind(f"SELECT 1 FROM t WHERE {{tenant@{column}}}")


def test_the_marker_must_still_be_the_first_term_of_a_where():
    with pytest.raises(TenantScopeViolation):
        TenantScopedQuery(7).bind("SELECT 1 FROM t WHERE x = 1 AND {tenant@AccountId}")


def test_the_closed_set_is_exactly_the_two_known_columns():
    assert TENANT_COLUMNS == {"client_id", "AccountId"}
