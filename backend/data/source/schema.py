"""FlexSchema table definitions — the partner's source shape.

Mirrors `stakeholder-docs/FlexSchema.txt`, the DDL scripted by the partner's team
from their `intranet` database on 20 Aug 2026. Field-by-field mapping and the six
open questions are in `docs/data/SOURCE-SCHEMA-MAPPING.md`.

Why this exists
---------------
The engine consumes the Silver Record Layout. The partner will hand us *this* shape.
Building a lakehouse in the source shape now, from data we already have, means
the Bronze -> Silver projection is written and tested before the real feed
arrives rather than after.

Three lookup tables referenced by foreign keys in the DDL were not supplied:
`EntityFiscalYearRules`, `PayFrequency` and `PayCodeCategory`. Where this module
has to stand one up, it is marked INFERRED and carries an `inferred` flag into
the data, so nothing here is mistaken later for something the partner told us.

This module defines shape only. It performs no I/O and holds no data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

# ---------------------------------------------------------------------------
# Fact table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Payroll:
    """`dbo.Payroll` — one row per employee per pay period per pay code.

    Clustered and partitioned on `PayrollRange_PS([Accountid])`: the partner
    already treats the account as the physical partition boundary, which is the
    same decision ADR-007 makes for the Warehouse: `client_id` leads every predicate.

    Note the two location columns. `LocationId` is NOT NULL and
    `WorksiteLocationId` is nullable; GA JTC counts jobs at a *worksite*, so
    which one is authoritative is open question Q3.
    """

    payroll_id: int
    account_id: int              # tenant key -> Account.AccountId
    employee_id: int             # -> Employee.EmployeeId
    entity_id: int               # -> Entity.EntityId (legal entity / FEIN)
    location_id: int             # -> Location.LocationId, NOT NULL
    pay_frequency_id: int        # -> PayFrequency.PayFrequencyId (lookup NOT supplied)
    pay_period_start: date
    pay_period_end: date
    pay_date: date | None        # nullable in source — Q1; BA-02 trims on this
    hours: Decimal | None        # nullable, DEFAULT 0 — Q2 vs BA-05
    wages: Decimal | None
    client_employee_id: str | None = None
    hourly_rate: Decimal | None = None
    is_full_time: bool | None = None
    is_salaried: bool | None = None
    pay_code_id: int | None = None       # CHECK constraint requires NOT NULL
    worksite_location_id: int | None = None
    inload_payroll_id: int | None = None
    create_date: datetime | None = None
    modify_date: datetime | None = None
    created_by: int = 0
    modified_by: int = 0


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Account:
    """`dbo.Account` — the client. This is the tenant."""

    account_id: int
    account_eid: int
    name: str
    billing_state: str | None = None
    billing_city: str | None = None
    billing_postal_code: str | None = None
    industry_type_id: int | None = None      # industry eligibility input
    account_status_id: int | None = None
    account_type_id: int | None = None
    actual_number_of_employees: int | None = None
    external_name: str | None = None
    create_date: datetime | None = None


@dataclass(frozen=True, slots=True)
class Entity:
    """`dbo.Entity` — legal entity. `parent_entity_id` self-references, giving
    the hierarchy that entity combination (CALC-06) needs.

    `fiscal_year_rules_id` is BA-01: the per-client fiscal window that is not
    derivable from payroll. Note it hangs off Entity, not Account, so fiscal
    year may vary by legal entity within one client — Q4.
    """

    entity_id: int
    account_id: int
    name: str
    federal_tax_id: str | None = None        # FEIN
    state_tax_id: str | None = None
    parent_entity_id: int | None = None
    entity_business_type_id: int | None = None
    fiscal_year_rules_id: int | None = None
    inception_date: date | None = None
    dissolution_date: date | None = None


@dataclass(frozen=True, slots=True)
class Location:
    """`dbo.Location` — a worksite. `open_date` / `close_date` matter: a site
    that opened mid-year is not a site with missing months.
    """

    location_id: int
    account_id: int
    entity_id: int
    location_name: str
    address_id: int
    client_location_id: str | None = None
    dba: str | None = None
    open_date: date | None = None
    close_date: date | None = None
    location_status_id: int = 2
    screening_status_id: int = 1


@dataclass(frozen=True, slots=True)
class Address:
    """`dbo.Address`. `zip_code_original` is nvarchar, so leading zeros survive
    — unlike the demo lakehouse, which stored postal codes as integers.
    """

    address_id: int
    street_address_1: str | None = None
    city_name: str | None = None
    state_county_zip_id: int | None = None
    zip_code_original: str | None = None
    state_original: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class StateCountyZip:
    """`dbo.StateCountyZip` — the county lookup.

    `county_name` is one of the four inputs missing from **credit value**:
    Georgia's tier is assigned by county and drives the per-job amount. Its
    presence here is what makes dollar certification a plumbing problem rather
    than a data-availability one.
    """

    state_county_zip_id: int
    state_abbr: str
    state_name: str
    county_name: str
    zip_code: str


@dataclass(frozen=True, slots=True)
class Employment:
    """`dbo.Employment` — hire, termination and job title.

    Grain is Q6: `current_location_id` alongside `hire_location_id` suggests the
    row is updated in place, which would mean worksite transfer history is lost
    and must be recovered from the Payroll rows themselves.
    """

    employment_id: int
    employee_id: int
    hire_location_id: int | None = None
    current_location_id: int | None = None
    status: str | None = None
    job_title: str | None = None
    hire_date: date | None = None
    start_date: date | None = None
    termination_date: date | None = None
    termination_reason: str | None = None
    employment_type: str | None = None       # nvarchar(2)
    wage_type: str | None = None             # nvarchar(1)
    employment_status: str | None = None     # nvarchar(1)
    department_number: str | None = None
    department_name: str | None = None


@dataclass(frozen=True, slots=True)
class PayCode:
    """`dbo.PayCode`.

    Carries `is_aca` and `is_futa` but **no state-JTC inclusion flag**. Whether
    `pay_code_category_id` supplies it is Q5 — the pay-code lookup already owed,
    now with a concrete column to confirm against. Until then BA-07 cannot be
    driven from source data.
    """

    pay_code_id: int
    account_id: int
    pay_code: str
    description: str | None = None
    is_aca: bool | None = None
    is_futa: bool = True
    pay_code_category_id: int | None = None


# ---------------------------------------------------------------------------
# Lookups referenced by FK but NOT supplied by the partner
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PayFrequency:
    """`dbo.PayFrequency` — **INFERRED. Not supplied by the partner.**

    `Payroll.PayFrequencyId` is a foreign key into this table. We never received
    it, which is the real reason BA-03 treats frequency as lineage only: we were
    reading a surrogate key without its lookup, not observing codes misbehave.

    The labels below are inferred from measured period spans in the reference
    dataset and are **not authoritative**:

        id 1 -> 7 days   (372,285 of 374,535 rows)
        id 2 -> 15, then 14 days
        id 4 -> 16 days, without exception

    `inferred` is carried into the data so this is never mistaken for something
    the partner told us. Requesting the real lookup is on the ask list.
    """

    pay_frequency_id: int
    name: str
    inferred: bool = True


@dataclass(frozen=True, slots=True)
class EntityFiscalYearRules:
    """`dbo.EntityFiscalYearRules` — **INFERRED. Not supplied by the partner.**

    BA-01. `Entity.FiscalYearRulesId` points here. This is very likely the
    "this is the client, this is the fiscal year" table the partner described, and its
    DDL is the highest-priority outstanding ask (Q4).

    The reference client runs 2023-07-28 to 2024-08-02 — a 53-week payroll calendar
    that no month-end fiscal year can express, which is why the engine takes an
    explicit `fiscal_window` rather than deriving one.
    """

    fiscal_year_rules_id: int
    name: str
    fiscal_year_begin: date | None = None
    fiscal_year_end: date | None = None
    rule_expression: str | None = None       # e.g. "Saturday nearest 31 July"
    inferred: bool = True


# ---------------------------------------------------------------------------
# The bundle a single client's data forms
# ---------------------------------------------------------------------------


@dataclass
class SourceDataset:
    """One client's data in the partner's source shape.

    `account` is the tenant. Everything else hangs off it, which is what makes a
    per-account export or a per-account partition natural.
    """

    account: Account
    entities: list[Entity] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    addresses: list[Address] = field(default_factory=list)
    state_county_zips: list[StateCountyZip] = field(default_factory=list)
    employments: list[Employment] = field(default_factory=list)
    pay_codes: list[PayCode] = field(default_factory=list)
    pay_frequencies: list[PayFrequency] = field(default_factory=list)
    fiscal_year_rules: list[EntityFiscalYearRules] = field(default_factory=list)
    payroll: list[Payroll] = field(default_factory=list, repr=False)

    def counts(self) -> dict[str, int]:
        return {
            "entities": len(self.entities),
            "locations": len(self.locations),
            "addresses": len(self.addresses),
            "state_county_zips": len(self.state_county_zips),
            "employments": len(self.employments),
            "pay_codes": len(self.pay_codes),
            "pay_frequencies": len(self.pay_frequencies),
            "fiscal_year_rules": len(self.fiscal_year_rules),
            "payroll": len(self.payroll),
        }


# Table order for writing: parents before children, so foreign keys resolve.
TABLE_ORDER = (
    "Account",
    "StateCountyZip",
    "Address",
    "EntityFiscalYearRules",
    "Entity",
    "Location",
    "PayFrequency",
    "PayCode",
    "Employment",
    "Payroll",
)
