"""Tests for `tools.triggers` — the partner's 4 stakeholder flags.

  - headcount_spike: a unit gained >= N employees year-over-year
  - wage_increase:  unit avg weekly wage rose >= pct YoY
  - new_fein:       new Entity_FEIN appeared
  - new_jurisdiction: new state appeared
"""
from __future__ import annotations

from tools.triggers import detect_triggers


def _row(emp, unit, hours=40, wages=800, fein="FEIN_1"):
    return {
        "Tax_Year": 2025,
        "Employee_ID": emp,
        "Worksite_ID": unit,
        "Pay_Period_Start": "2025-01-01",
        "Pay_Period_End": "2025-01-07",
        "Pay_Date": "2025-01-12",
        "Hours_Worked": hours,
        "Gross_Wages": wages,
        "Entity_FEIN": fein,
        "Job_Title": "x",
        "Pay_Code": "Regular",
    }


# ---------------------------------------------------------------------------
# Headcount spike
# ---------------------------------------------------------------------------


def test_headcount_spike_fires_when_unit_grows_by_threshold():
    """5+ new employees at a unit triggers headcount_spike."""
    prior = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(3)]
    current = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(8)]  # +5
    triggers = detect_triggers(prior, current)
    spikes = [t for t in triggers if t["type"] == "headcount_spike"]
    assert len(spikes) == 1
    s = spikes[0]
    assert s["unit"] == "GA_ATL_HQ"
    assert s["jurisdiction"] == "GA"
    assert s["delta"] == 5
    assert s["severity"] == "medium"


def test_headcount_spike_high_severity_at_10():
    """A +10 spike is escalated to high severity."""
    prior = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(3)]
    current = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(13)]  # +10
    triggers = detect_triggers(prior, current)
    spikes = [t for t in triggers if t["type"] == "headcount_spike"]
    assert spikes[0]["severity"] == "high"


def test_headcount_spike_does_not_fire_below_threshold():
    """A +3 change is below the default 5-employee threshold."""
    prior = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(3)]
    current = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(6)]  # +3
    triggers = detect_triggers(prior, current)
    assert [t for t in triggers if t["type"] == "headcount_spike"] == []


def test_headcount_spike_custom_threshold():
    prior = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(3)]
    current = [_row(f"E{i:03}", "GA_ATL_HQ") for i in range(6)]  # +3
    triggers = detect_triggers(prior, current, headcount_spike_min=2)
    spikes = [t for t in triggers if t["type"] == "headcount_spike"]
    assert spikes[0]["delta"] == 3


# ---------------------------------------------------------------------------
# Wage increase
# ---------------------------------------------------------------------------


def test_wage_increase_fires_at_default_10pct():
    """Avg hourly wage rising 12% triggers wage_increase."""
    prior = [_row("E1", "GA_ATL_HQ", hours=40, wages=800)]  # $20/hr
    current = [_row("E1", "GA_ATL_HQ", hours=40, wages=900)]  # $22.50/hr +12.5%
    triggers = detect_triggers(prior, current)
    wage = [t for t in triggers if t["type"] == "wage_increase"]
    assert len(wage) == 1
    assert wage[0]["jurisdiction"] == "GA"
    assert wage[0]["delta_pct"] >= 0.10


def test_wage_increase_does_not_fire_below_threshold():
    """5% increase shouldn't trigger at default 10% threshold."""
    prior = [_row("E1", "GA_ATL_HQ", hours=40, wages=800)]
    current = [_row("E1", "GA_ATL_HQ", hours=40, wages=840)]  # +5%
    triggers = detect_triggers(prior, current)
    assert [t for t in triggers if t["type"] == "wage_increase"] == []


def test_wage_increase_custom_threshold():
    prior = [_row("E1", "GA_ATL_HQ", hours=40, wages=800)]
    current = [_row("E1", "GA_ATL_HQ", hours=40, wages=840)]  # +5%
    triggers = detect_triggers(prior, current, wage_increase_min_pct=0.03)
    assert any(t["type"] == "wage_increase" for t in triggers)


# ---------------------------------------------------------------------------
# New FEIN
# ---------------------------------------------------------------------------


def test_new_fein_fires_when_new_entity_appears():
    prior = [_row("E1", "GA_ATL_HQ", fein="FEIN_1")]
    current = [
        _row("E1", "GA_ATL_HQ", fein="FEIN_1"),
        _row("E2", "NY_NYC", fein="FEIN_NEW"),
    ]
    triggers = detect_triggers(prior, current)
    fein_triggers = [t for t in triggers if t["type"] == "new_fein"]
    assert len(fein_triggers) == 1
    assert fein_triggers[0]["fein"] == "FEIN_NEW"
    assert fein_triggers[0]["severity"] == "high"


def test_new_fein_does_not_fire_when_fein_existed_before():
    prior = [_row("E1", "GA_ATL_HQ", fein="FEIN_1")]
    current = [_row("E1", "GA_ATL_HQ", fein="FEIN_1")]
    triggers = detect_triggers(prior, current)
    assert [t for t in triggers if t["type"] == "new_fein"] == []


# ---------------------------------------------------------------------------
# New jurisdiction
# ---------------------------------------------------------------------------


def test_new_jurisdiction_fires_when_new_state_appears():
    prior = [_row("E1", "GA_ATL_HQ")]
    current = [
        _row("E1", "GA_ATL_HQ"),
        _row("E2", "TX_DAL_OPS"),
    ]
    triggers = detect_triggers(prior, current)
    juris_triggers = [t for t in triggers if t["type"] == "new_jurisdiction"]
    assert len(juris_triggers) == 1
    assert juris_triggers[0]["jurisdiction"] == "TX"
    assert juris_triggers[0]["severity"] == "high"


# ---------------------------------------------------------------------------
# Empty / no-op
# ---------------------------------------------------------------------------


def test_empty_inputs_produce_no_triggers():
    assert detect_triggers([], []) == []


def test_identical_snapshots_produce_no_triggers():
    snap = [_row("E1", "GA_ATL_HQ")]
    assert detect_triggers(snap, snap) == []
