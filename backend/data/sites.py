"""Physical site registry for MeridianCore Logistics.

Each site is a concrete location (warehouse, office, distribution center) with
GPS coordinates so the frontend US map can place a circle marker. Columns:

  site_id            Short unique key, e.g. "GA_ATL_HQ"
  name               Display name
  state              Two-letter state code
  county             County name (matches payroll location_county where applicable)
  city               City name (for labels)
  lat / lon          WGS-84 decimal degrees (approximate city-centre)
  status             "active" | "expanding" | "contracting" | "planned"
  opened             ISO date the site was established (or None for legacy)
  headcount_est      Current estimated headcount (integer)
  projected_fte_delta_q3   Explicit Q3 forecast delta vs today (+n new hires or −n losses)
  credit_codes       Rule-pack codes currently in scope for this site
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Site dataclass
# ---------------------------------------------------------------------------

@dataclass
class Site:
    site_id: str
    name: str
    state: str
    county: str
    city: str
    lat: float
    lon: float
    status: str          # active | expanding | contracting | planned
    opened: str | None   # ISO-8601 date or None for legacy pre-window sites
    headcount_est: int
    projected_fte_delta_q3: float   # explicit forecast; positive = hiring, negative = reduction
    credit_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "state": self.state,
            "county": self.county,
            "city": self.city,
            "lat": self.lat,
            "lon": self.lon,
            "status": self.status,
            "opened": self.opened,
            "headcount_est": self.headcount_est,
            "projected_fte_delta_q3": self.projected_fte_delta_q3,
            "credit_codes": self.credit_codes,
        }


# ---------------------------------------------------------------------------
# Registry  (all coordinates are approximate city-centre; not exact facility address)
# ---------------------------------------------------------------------------

SITES: list[Site] = [
    # ─── Georgia: HQ + three distribution / ops centres ──────────────────────
    Site(
        site_id="GA_ATL_HQ",
        name="Atlanta HQ",
        state="GA", county="Fulton", city="Atlanta",
        lat=33.749, lon=-84.388,
        status="active", opened=None,
        headcount_est=48,
        projected_fte_delta_q3=+6.0,
        credit_codes=["GA_JTC", "FED_WOTC"],
    ),
    Site(
        site_id="GA_SAV_DC",
        name="Savannah Distribution Center",
        state="GA", county="Chatham", city="Savannah",
        lat=32.080, lon=-81.099,
        status="expanding", opened="2023-03-01",
        headcount_est=32,
        projected_fte_delta_q3=+4.0,
        credit_codes=["GA_JTC", "FED_WOTC"],
    ),
    Site(
        site_id="GA_MAC_OPS",
        name="Macon Operations",
        state="GA", county="Bibb", city="Macon",
        lat=32.838, lon=-83.633,
        status="active", opened="2021-06-15",
        headcount_est=15,
        projected_fte_delta_q3=0.0,
        credit_codes=["GA_JTC"],
    ),
    Site(
        site_id="GA_CUM_OPS",
        name="Cumberland Center",
        state="GA", county="Cobb", city="Cumberland",
        lat=33.897, lon=-84.548,
        status="contracting", opened="2020-09-01",
        headcount_est=14,
        projected_fte_delta_q3=-10.0,   # known Q3 reduction (lease non-renewal)
        credit_codes=["GA_JTC"],
    ),
    # ─── New York: Manhattan office + Brooklyn hub (contracting YoY) ─────────
    Site(
        site_id="NY_NYC_OFC",
        name="Manhattan Office",
        state="NY", county="New York", city="New York",
        lat=40.712, lon=-74.006,
        status="contracting", opened=None,
        headcount_est=18,
        projected_fte_delta_q3=-3.0,
        credit_codes=["NY_EXCELSIOR", "FED_WOTC"],
    ),
    Site(
        site_id="NY_BKN_HUB",
        name="Brooklyn Hub",
        state="NY", county="Kings", city="Brooklyn",
        lat=40.678, lon=-73.944,
        status="active", opened="2025-01-10",
        headcount_est=10,
        projected_fte_delta_q3=+2.0,
        credit_codes=["NY_EXCELSIOR", "FED_WOTC"],
    ),
    # ─── South Carolina: Charleston port ops (growing) + Greenville ──────────
    Site(
        site_id="SC_CHS_PORT",
        name="Charleston Port Ops",
        state="SC", county="Charleston", city="Charleston",
        lat=32.776, lon=-79.931,
        status="expanding", opened="2025-10-01",
        headcount_est=22,
        projected_fte_delta_q3=+5.0,
        credit_codes=["SC_JTC", "FED_WOTC"],
    ),
    Site(
        site_id="SC_GVL_FAC",
        name="Greenville Facility",
        state="SC", county="Greenville", city="Greenville",
        lat=34.852, lon=-82.395,
        status="active", opened="2022-07-01",
        headcount_est=12,
        projected_fte_delta_q3=+1.0,
        credit_codes=["SC_JTC"],
    ),
    # ─── Texas: three hubs (no state income-tax rule pack) ───────────────────
    Site(
        site_id="TX_AUS_TECH",
        name="Austin Tech Hub",
        state="TX", county="Travis", city="Austin",
        lat=30.267, lon=-97.743,
        status="active", opened="2025-01-15",
        headcount_est=16,
        projected_fte_delta_q3=+3.0,
        credit_codes=["FED_WOTC"],
    ),
    Site(
        site_id="TX_HOU_HUB",
        name="Houston Distribution Hub",
        state="TX", county="Harris", city="Houston",
        lat=29.760, lon=-95.370,
        status="active", opened="2025-10-01",
        headcount_est=18,
        projected_fte_delta_q3=+2.0,
        credit_codes=["FED_WOTC"],
    ),
    Site(
        site_id="TX_DAL_REG",
        name="Dallas Regional",
        state="TX", county="Dallas", city="Dallas",
        lat=32.776, lon=-96.797,
        status="expanding", opened="2026-04-01",
        headcount_est=8,
        projected_fte_delta_q3=+5.0,
        credit_codes=["FED_WOTC"],
    ),
    # ─── North Carolina: Charlotte distribution + Raleigh office (new) ───────
    Site(
        site_id="NC_CLT_DC",
        name="Charlotte Distribution Center",
        state="NC", county="Mecklenburg", city="Charlotte",
        lat=35.227, lon=-80.843,
        status="expanding", opened="2025-04-01",
        headcount_est=16,
        projected_fte_delta_q3=+4.0,
        credit_codes=["NC_JTEC", "FED_WOTC"],
    ),
    Site(
        site_id="NC_RDU_OFC",
        name="Raleigh-Durham Office",
        state="NC", county="Wake", city="Raleigh",
        lat=35.779, lon=-78.638,
        status="active", opened="2025-07-01",
        headcount_est=9,
        projected_fte_delta_q3=+2.0,
        credit_codes=["NC_JTEC"],
    ),
    # ─── Tennessee: Nashville distribution (large; triggers TN JTC) ──────────
    Site(
        site_id="TN_BNA_DC",
        name="Nashville Distribution Center",
        state="TN", county="Davidson", city="Nashville",
        lat=36.162, lon=-86.781,
        status="expanding", opened="2025-03-01",
        headcount_est=28,
        projected_fte_delta_q3=+7.0,
        credit_codes=["TN_JTC", "FED_WOTC"],
    ),
    Site(
        site_id="TN_MEM_DC",
        name="Memphis Fulfillment Center",
        state="TN", county="Shelby", city="Memphis",
        lat=35.149, lon=-90.048,
        status="active", opened="2025-06-01",
        headcount_est=16,
        projected_fte_delta_q3=+3.0,
        credit_codes=["TN_JTC", "FED_WOTC"],
    ),
    # ─── Florida: Jacksonville hub + Miami office (new) ──────────────────────
    Site(
        site_id="FL_JAX_HUB",
        name="Jacksonville Hub",
        state="FL", county="Duval", city="Jacksonville",
        lat=30.332, lon=-81.655,
        status="expanding", opened="2025-06-01",
        headcount_est=16,
        projected_fte_delta_q3=+4.0,
        credit_codes=["FL_QTI", "FED_WOTC"],
    ),
    Site(
        site_id="FL_MIA_OFC",
        name="Miami Regional Office",
        state="FL", county="Miami-Dade", city="Miami",
        lat=25.775, lon=-80.208,
        status="active", opened="2025-09-01",
        headcount_est=8,
        projected_fte_delta_q3=+2.0,
        credit_codes=["FL_QTI"],
    ),
    # ─── Ohio: Columbus facility + Cincinnati hub (new) ──────────────────────
    Site(
        site_id="OH_CMH_FAC",
        name="Columbus Facility",
        state="OH", county="Franklin", city="Columbus",
        lat=39.961, lon=-82.999,
        status="expanding", opened="2025-04-01",
        headcount_est=13,
        projected_fte_delta_q3=+3.0,
        credit_codes=["OH_JCTC", "FED_WOTC"],
    ),
    Site(
        site_id="OH_CVG_HUB",
        name="Cincinnati Hub",
        state="OH", county="Hamilton", city="Cincinnati",
        lat=39.103, lon=-84.512,
        status="active", opened="2025-08-01",
        headcount_est=8,
        projected_fte_delta_q3=+1.0,
        credit_codes=["OH_JCTC"],
    ),
    # ─── Colorado: Denver office (new; Enterprise Zone) ──────────────────────
    Site(
        site_id="CO_DEN_OFC",
        name="Denver Regional Office",
        state="CO", county="Denver", city="Denver",
        lat=39.739, lon=-104.990,
        status="active", opened="2025-05-01",
        headcount_est=13,
        projected_fte_delta_q3=+2.0,
        credit_codes=["CO_EZ", "FED_WOTC"],
    ),
    # ─── Virginia: Northern Virginia hub (new; triggers VA MBJF) ─────────────
    Site(
        site_id="VA_IAD_HUB",
        name="Northern Virginia Hub",
        state="VA", county="Fairfax", city="Tysons Corner",
        lat=38.919, lon=-77.228,
        status="expanding", opened="2025-02-01",
        headcount_est=32,
        projected_fte_delta_q3=+6.0,
        credit_codes=["VA_MBJF", "FED_WOTC"],
    ),
]

# Lookup by site_id.
SITES_BY_ID: dict[str, Site] = {s.site_id: s for s in SITES}


def worksite_name(worksite_id: str) -> str:
    """Human-readable worksite label (e.g. GA_MAC_OPS → 'Macon Operations').

    Falls back to the raw id when the worksite isn't in the registry so nothing
    ever renders blank.
    """
    site = SITES_BY_ID.get(str(worksite_id))
    return site.name if site else str(worksite_id)


def get_all_sites() -> list[dict]:
    """Return all sites as JSON-serialisable dicts."""
    return [s.to_dict() for s in SITES]


def get_sites_by_state(state: str) -> list[dict]:
    """Return sites for a specific state."""
    return [s.to_dict() for s in SITES if s.state == state.upper()]
