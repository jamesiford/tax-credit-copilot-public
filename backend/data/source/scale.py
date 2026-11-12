"""A deterministic, synthetic source dataset generator at scale: N accounts, M payroll rows, realistic skew. [05.6]

Used by the sample-lakehouse build, the scale work (prompt 08) and the read-mode spike (prompt 10). Everything is invented:
account names are `Scale Account NNNNN`, ids start well away from any demo or customer range, employees are numbers, and no
table carries a name, a date of birth, a phone or an email. The same `seed` gives the same datasets byte for byte.

Skew: account sizes follow a power law (`1 / rank ** exponent`), so there are many small accounts and a few very large ones,
as in a real book. The rows are exact: the accounts' payroll rows sum to `rows`.

Shape: one fiscal year of biweekly pay per employee at most 26 periods deep, a handful of locations per account in a handful
of states, four pay codes, no lookup tables (`PayFrequency` and `EntityFiscalYearRules` are app-owned and are not generated).
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from .schema import Account, Address, Employment, Entity, Location, PayCode, Payroll, SourceDataset, StateCountyZip

FIRST_ACCOUNT_ID = 910_001
_STATES = (("GA", "Georgia", ("Fulton", "Cobb", "Gwinnett", "Chatham")), ("SC", "South Carolina", ("Greenville", "Charleston", "Richland")),
           ("NC", "North Carolina", ("Wake", "Mecklenburg", "Guilford")), ("TN", "Tennessee", ("Davidson", "Shelby", "Knox")))
_CODES = (("REG", "Regular hourly"), ("OT", "Overtime"), ("BON", "Bonus"), ("PTO", "Paid time off"))
_TITLES = ("Associate", "Crew member", "Technician", "Driver", "Clerk", "Supervisor")
_PERIODS = 26
_FISCAL_START = date(2023, 1, 6)


def account_sizes(accounts: int, rows: int, exponent: float = 1.1) -> list[int]:
    """Rows per account: a power law summing exactly to `rows`, every account holding at least one."""
    if accounts < 1 or rows < accounts:
        raise ValueError("need at least one account and at least one row per account")
    weights = [1 / (rank + 1) ** exponent for rank in range(accounts)]
    total = sum(weights)
    sizes = [max(1, int(rows * w / total)) for w in weights]
    sizes[0] += rows - sum(sizes)  # the remainder lands on the largest account, so the total is exact
    return sizes


def _dimensions(rng: random.Random, account_id: int, employees: int) -> tuple:
    """Entity, locations and addresses for one account, with ids that are unique across accounts."""
    entity = Entity(entity_id=account_id * 100 + 1, account_id=account_id, name=f"Scale Account {account_id - FIRST_ACCOUNT_ID + 1:05d} LLC",
                    federal_tax_id=f"{rng.randrange(10, 99)}-{rng.randrange(1_000_000, 9_999_999)}", inception_date=date(2015, 1, 1))
    count = max(1, min(60, employees // 8 or 1))
    addresses, locations = [], []
    for j in range(count):
        state, _name, counties = _STATES[rng.randrange(len(_STATES))]
        address_id = account_id * 1000 + j + 1
        addresses.append(Address(address_id=address_id, street_address_1=f"{100 + j} Example Street", city_name=f"Town {j + 1}",
                                 state_county_zip_id=(_STATES.index(next(s for s in _STATES if s[0] == state)) + 1) * 10 + counties.index(rng.choice(counties)) % 3,
                                 zip_code_original=f"{30000 + rng.randrange(900):05d}", state_original=state))
        locations.append(Location(location_id=address_id, account_id=account_id, entity_id=entity.entity_id, location_name=f"Site {j + 1}",
                                  address_id=address_id, client_location_id=f"S{j + 1:03d}", open_date=date(2018, 1, 1)))
    return entity, locations, addresses


def _geography() -> list[StateCountyZip]:
    out = []
    for s, (abbr, name, counties) in enumerate(_STATES, start=1):
        for c, county in enumerate(counties[:3]):
            out.append(StateCountyZip(state_county_zip_id=s * 10 + c, state_abbr=abbr, state_name=name, county_name=f"{county} County", zip_code=f"{30000 + s * 100 + c}"))
    return out


def _payroll(rng: random.Random, account_id: int, rows: int, locations: list[Location], entity_id: int, first_id: int):
    periods = min(_PERIODS, rows)
    employees = math.ceil(rows / periods)
    home = [locations[rng.randrange(len(locations))].location_id for _ in range(employees)]
    rates = [Decimal(rng.randrange(1100, 3200)) / 100 for _ in range(employees)]
    payroll = []
    for k in range(rows):
        e, p = k % employees, k // employees
        start = _FISCAL_START + timedelta(days=14 * p)
        end = start + timedelta(days=13)
        hours = Decimal(rng.randrange(2400, 8800)) / 100
        code = 2 if rng.random() < 0.04 else 1
        payroll.append(Payroll(
            payroll_id=first_id + k, account_id=account_id, employee_id=account_id * 100_000 + e + 1, entity_id=entity_id,
            location_id=home[e], pay_frequency_id=3, pay_period_start=start, pay_period_end=end, pay_date=end + timedelta(days=5),
            hours=hours, wages=(hours * rates[e]).quantize(Decimal("0.01")), client_employee_id=f"E{e + 1:06d}", hourly_rate=rates[e],
            is_full_time=bool(hours >= 60), is_salaried=False, pay_code_id=account_id * 10 + code, worksite_location_id=home[e],
            create_date=datetime(2024, 1, 1), modify_date=datetime(2024, 1, 1)))
    return payroll, employees


def generate(accounts: int, rows: int, seed: int = 1, exponent: float = 1.1) -> list[SourceDataset]:
    """`accounts` synthetic datasets holding exactly `rows` payroll rows between them, deterministic in `seed`."""
    rng = random.Random(seed)
    sizes = account_sizes(accounts, rows, exponent)
    geography, datasets, next_payroll_id = _geography(), [], 1
    for i, size in enumerate(sizes):
        account_id = FIRST_ACCOUNT_ID + i
        entity, locations, addresses = _dimensions(rng, account_id, math.ceil(size / min(_PERIODS, size)))
        payroll, employees = _payroll(rng, account_id, size, locations, entity.entity_id, next_payroll_id)
        next_payroll_id += size
        account = Account(account_id=account_id, account_eid=account_id, name=f"Scale Account {i + 1:05d}", billing_state="GA",
                          actual_number_of_employees=employees, create_date=datetime(2020, 1, 1))
        codes = [PayCode(pay_code_id=account_id * 10 + n, account_id=account_id, pay_code=code, description=text, is_aca=True, is_futa=True)
                 for n, (code, text) in enumerate(_CODES, start=1)]
        employments = [Employment(employment_id=account_id * 100_000 + e + 1, employee_id=account_id * 100_000 + e + 1,
                                  job_title=_TITLES[(e + i) % len(_TITLES)], status="active") for e in range(employees)]
        datasets.append(SourceDataset(account=account, entities=[entity], locations=locations, addresses=addresses,
                                      state_county_zips=geography if i == 0 else [], employments=employments, pay_codes=codes,
                                      pay_frequencies=[], fiscal_year_rules=[], payroll=payroll))
    return datasets
