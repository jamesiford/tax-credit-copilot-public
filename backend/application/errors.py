"""Typed failures: a dependency that is missing, unreachable or uninitialised. [03.3, 03.7]

An outage used to arrive as an empty list or an opaque 500, and nothing told a caller
which dependency was down or what to do about it. These carry the three facts a person
needs: *which* dependency, *why*, and *the remedy*. `api` turns one into a 503 that
says so, and a read that can still answer part of a page reports it in a `degraded` list
instead of raising (`DependencyUnavailable.as_degraded`).

Dependency names are a closed convention, not free text: `source_lakehouse`,
`source_sql`, `claims_store`, `operational_store`, and `lookup:<name>` for one lookup table.
"""
from __future__ import annotations

from typing import Any


class DependencyUnavailable(RuntimeError):
    """A named dependency cannot answer. `remedy` is what an operator does next."""

    def __init__(self, dependency: str, reason: str, remedy: str, *, impact: str = "") -> None:
        super().__init__(f"{dependency} unavailable: {reason} {remedy}".strip())
        self.dependency = dependency
        self.reason = reason
        self.remedy = remedy
        self.impact = impact
        #: How long a caller that remembers this failure should not retry it. Set by that caller.
        self.retry_seconds = 60.0

    def as_degraded(self, impact: str | None = None) -> dict[str, Any]:
        """The entry a response carries in its `degraded` list."""
        return {
            "dependency": self.dependency,
            "impact": impact or self.impact or self.reason,
            "remedy": self.remedy,
        }

    def as_detail(self) -> dict[str, Any]:
        return {"detail": str(self), "dependency": self.dependency, "reason": self.reason, "remedy": self.remedy}


class SourceNotConfigured(DependencyUnavailable):
    """`DATA_SOURCE` resolves to the lakehouse but no lakehouse is named."""

    def __init__(self, missing: tuple[str, ...] = ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE")) -> None:
        names = " and ".join(missing)
        super().__init__(
            "source_lakehouse",
            f"the data source is the lakehouse but {names} {'is' if len(missing) == 1 else 'are'} not set.",
            f"Set {names} (and ONELAKE_ENDPOINT for a private-link workspace). "
            "Set DATA_SOURCE=csv only for the local test fixture.",
            impact="no client or payroll data can be read",
        )
        self.missing = missing


class SourceSchemaMismatch(DependencyUnavailable):
    """A lake table lacks columns the mapping marks required, so the engine cannot read it faithfully."""

    def __init__(self, table: str, physical: str, missing: tuple[str, ...]) -> None:
        names = ", ".join(missing)
        super().__init__(
            "source_lakehouse",
            f"table {physical} (logical {table}) has no column for required field(s): {names}.",
            "Run `python scripts/validate-source-schema.py` for the full report, then correct the column names "
            "in the source mapping (SOURCE_MAPPING_FILE). A field the engine needs but the lake does not hold needs code.",
            impact=f"{table} cannot be read, so no payroll can be projected",
        )
        self.table, self.missing = table, missing


class UnmappedPayCodes(DependencyUnavailable):
    """Under the `strict` policy, payroll carries pay codes no provider maps; the calculation is blocked, never run on a guess."""

    def __init__(self, codes: tuple[str, ...], rows: int) -> None:
        shown = ", ".join(codes[:20]) + (f" and {len(codes) - 20} more" if len(codes) > 20 else "")
        super().__init__(
            "lookup:pay_code_category",
            f"{len(codes)} pay code(s) covering {rows} payroll row(s) are not mapped to a canonical category: {shown}.",
            "Author the mapping with `python scripts/lookups.py import pay_code_category --account <id> <file.csv>`, or have the "
            "customer's PayCodeCategory supplied. PAY_CODE_POLICY=assume carries the codes through unmapped (flagged, counted).",
            impact="payroll for this client is not calculated: an unmapped code is dropped by the state's whitelist and eligibility would read zero",
        )
        self.codes, self.rows = codes, rows


class FiscalRulesMissing(DependencyUnavailable):
    """Under the `strict` policy, a client has no fiscal rule from any provider."""

    def __init__(self, account_id: int) -> None:
        super().__init__(
            "lookup:entity_fiscal_year_rules",
            f"account {account_id} has no fiscal year rule from the source or an override.",
            "Author one with `python scripts/lookups.py import entity_fiscal_year_rules --account <id> <file.json>`, or set "
            "FISCAL_RULES_POLICY=assume to use a calendar year (flagged as assumed).",
            impact="the client's fiscal window, and so its base year, cannot be determined",
        )


class SilverNotBuilt(DependencyUnavailable):
    """`SOURCE_SILVER=require` and an account has no Silver partition."""

    def __init__(self, account_id: int) -> None:
        super().__init__(
            "source_silver", f"account {account_id} has no Silver partition.",
            "Run scripts/fabric/build-silver.py for it, or set SOURCE_SILVER=auto to fall back to the raw read.",
            impact="this client's payroll is not loaded",
        )


class AccountTooLarge(DependencyUnavailable):
    """One account's payroll is larger than the configured bound, so it is refused rather than loaded into memory."""

    def __init__(self, account_id: int, rows: int, limit: int) -> None:
        super().__init__(
            "source_lakehouse",
            f"account {account_id} has {rows:,} payroll rows, over SOURCE_MAX_ACCOUNT_ROWS ({limit:,}).",
            "Raise SOURCE_MAX_ACCOUNT_ROWS if the host has the memory, or use the pre-aggregated read "
            "(docs/architecture/SCALE-READS.md); a client-year drill-through reads only that year.",
            impact="this client's payroll is not loaded",
        )
        self.account_id, self.rows, self.limit = account_id, rows, limit


class ReferenceNotConfigured(DependencyUnavailable):
    """The certified reference run was asked for, and no deployment account is named as its subject."""

    def __init__(self) -> None:
        super().__init__(
            "reference_dataset",
            "no account is configured as the certified reference (REFERENCE_ACCOUNT_ID is unset).",
            "Set REFERENCE_ACCOUNT_ID to the reference account's id, only where the reference dataset is loaded. "
            "Every other screen works without it.",
            impact="the sealed reference views (evidence pack, back-test, certified figures) are unavailable",
        )


#: A bug in our own code is not an outage. These propagate (a 500 with a trace) instead of
#: being reported as a dependency that is down, which is how an `except Exception` turned a
#: typo into "the claims store is unavailable".
PROGRAMMING_ERRORS = (TypeError, AttributeError, KeyError, NameError, AssertionError, ImportError)

#: (lower-cased fragment of the driver's message, reason, remedy). First match wins.
_FAILURE_MEANINGS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("invalid object name", "no such table", "no such column", "invalid column name"),
     "a table or schema it needs is missing (the store was never initialised, or is behind its migrations).",
     "Run `python scripts/apply-migrations.py --target deployed` (a new Warehouse also needs `--bootstrap`)."),
    (("permission was denied", "select permission", "insert permission", "login failed", "not authorized",
      "authorizationfailure", "403"),
     "the identity can connect but has no permission on the store.",
     "Grant the app identity access: `python scripts/grant-warehouse-sql.py` and the Fabric workspace role."),
    (("not set", "warehousenotconfigured"),
     "the store is not configured.",
     "Set WAREHOUSE_SERVER and WAREHOUSE_DATABASE (or choose a local store with ENVIRONMENT=local)."),
    (("timed out", "timeout", "08001", "could not open a connection", "name or service not known",
      "getaddrinfo", "dns", "network-related", "connection refused", "connect"),
     "the server could not be reached.",
     "Check the server name, that the capacity is running, and that this machine's network and DNS reach it."),
)


def as_dependency_failure(dependency: str, exc: BaseException, *, impact: str = "") -> DependencyUnavailable | None:
    """A typed failure for `exc`, or None when it is a bug that must propagate.

    The reason names the class of failure and never echoes the driver's message, which can carry a
    server name or a login; the full text is logged once by the caller.
    """
    if isinstance(exc, DependencyUnavailable):
        return exc
    if isinstance(exc, PROGRAMMING_ERRORS):
        return None
    text = f"{type(exc).__name__}: {exc}".lower()
    for fragments, reason, remedy in _FAILURE_MEANINGS:
        if any(fragment in text for fragment in fragments):
            return DependencyUnavailable(dependency, reason, remedy, impact=impact)
    return DependencyUnavailable(
        dependency, f"it failed with {type(exc).__name__}.", "See the application log for the detail.", impact=impact,
    )
