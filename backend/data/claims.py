"""Credit claims registry for MeridianCore Logistics.

A claim represents a formal (or pending) filing for a specific credit in a
specific tax year. Statuses:
  eligible     — we compute they qualify; not yet filed
  filed        — submission sent to the jurisdiction
  in_review    — jurisdiction acknowledged, review underway
  approved     — credit approved; value confirmed
  missing_docs — flagged by jurisdiction for additional documentation

Claims are static for the demo (no real filing workflow). The evidence_pack_id
links to the EvidencePack registry so users can drill into the audit trail.
"""
from __future__ import annotations

from typing import Any

CLAIMS: list[dict[str, Any]] = [
    {
        "claim_id": "CLM-2024-GA-001",
        "credit_code": "GA_JTC",
        "credit_name": "Georgia Jobs Tax Credit",
        "jurisdiction": "GA",
        "tax_year": 2024,
        "status": "approved",
        "qualifying_jobs": 12.67,
        "annual_credit_usd": 44_345,
        "lifetime_credit_usd": 221_725,
        "benefit_period_years": 5,
        "filing_date": "2026-02-18",
        "approved_date": "2026-05-20",
        "evidence_pack_id": "EP-001",
        "citation": "OCGA § 48-7-40",
        "notes": "Tier 1 county award. First claim under the growth initiative.",
    },
    {
        "claim_id": "CLM-2025-SC-001",
        "credit_code": "SC_JTC",
        "credit_name": "South Carolina Jobs Tax Credit",
        "jurisdiction": "SC",
        "tax_year": 2025,
        "status": "eligible",
        "qualifying_jobs": 8.20,
        "annual_credit_usd": 12_300,
        "lifetime_credit_usd": 61_500,
        "benefit_period_years": 5,
        "filing_date": None,
        "approved_date": None,
        "evidence_pack_id": "EP-002",
        "citation": "S.C. Code § 12-6-3360",
        "notes": "Charleston Port Ops growth drove SC above the 5-job threshold in Q4 2025. Filing window opens Jan 2026.",
    },
    {
        "claim_id": "CLM-2025-FED-001",
        "credit_code": "FED_WOTC",
        "credit_name": "Federal Work Opportunity Tax Credit (lite)",
        "jurisdiction": "US",
        "tax_year": 2025,
        "status": "approved",
        "qualifying_jobs": 87,   # new-hires-in-window basis
        "annual_credit_usd": 208_800,
        "lifetime_credit_usd": 208_800,
        "benefit_period_years": 1,
        "filing_date": "2026-01-28",
        "approved_date": "2026-04-15",
        "evidence_pack_id": "EP-003",
        "citation": "IRC § 51",
        "notes": "Submitted with IRS Form 5884. DOL ETA certification finalized for all 87 hires; refund received Q2 FY26.",
    },
    {
        "claim_id": "CLM-2025-TN-001",
        "credit_code": "TN_JTC",
        "credit_name": "Tennessee Job Tax Credit",
        "jurisdiction": "TN",
        "tax_year": 2025,
        "status": "missing_docs",
        "qualifying_jobs": 11.5,
        "annual_credit_usd": 51_750,
        "lifetime_credit_usd": 258_750,
        "benefit_period_years": 5,
        "filing_date": "2026-02-10",
        "approved_date": None,
        "evidence_pack_id": "EP-004",
        "citation": "T.C.A. § 67-4-2109",
        "notes": "TN DOR requested payroll register for Nashville DC and proof of Enhanced Opportunity Zone designation. Due 2026-06-30.",
    },
    {
        "claim_id": "CLM-2026-VA-001",
        "credit_code": "VA_MBJF",
        "credit_name": "Virginia Major Business Facility Job Tax Credit",
        "jurisdiction": "VA",
        "tax_year": 2026,
        "status": "eligible",
        "qualifying_jobs": 7.0,
        "annual_credit_usd": 7_000,
        "lifetime_credit_usd": 35_000,
        "benefit_period_years": 5,
        "filing_date": None,
        "approved_date": None,
        "evidence_pack_id": "EP-005",
        "citation": "Va. Code § 58.1-439",
        "notes": "Northern Virginia Hub crossed the 25-job threshold in Q1 2026. First eligible tax year is 2026.",
    },
]

CLAIMS_BY_ID: dict[str, dict] = {c["claim_id"]: c for c in CLAIMS}


def get_all_claims() -> list[dict]:
    return list(CLAIMS)


def get_claims_by_status(status: str) -> list[dict]:
    return [c for c in CLAIMS if c["status"] == status]


def get_claims_by_state(state: str) -> list[dict]:
    return [c for c in CLAIMS if c["jurisdiction"] == state.upper()]
