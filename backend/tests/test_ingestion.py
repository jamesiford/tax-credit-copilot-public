"""Tests for the Data Ingestion endpoints (Stage 1)."""
from __future__ import annotations


def test_ingestion_overview_shape(client):
    r = client.get("/api/ingestion/2025?state=GA")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "GA"
    assert body["tax_year"] == 2025
    # Transform is legible: field map + raw sample + staged pipeline.
    assert body["field_map"] and all("source" in f and "canonical" in f for f in body["field_map"])
    assert body["raw_sample"] and "Pay_Date" in body["raw_sample"][0]
    assert len(body["pipeline"]) == 4
    totals = body["totals"]
    assert totals["distinct_employees"] > 0
    assert totals["source_rows"] >= totals["fiscal_year_rows"] >= totals["includable_rows"]
    # QC block present with a resolution surface.
    assert "summary" in body["qc"] and "exceptions" in body["qc"]
    assert "unresolved" in body["qc"]["summary"]


def test_ingestion_pay_code_split_present(client):
    body = client.get("/api/ingestion/2025?state=GA").json()
    split = body["pay_code_split"]
    assert split and all("pay_code" in s and "count" in s for s in split)


def test_ingestion_resolve_and_reopen(client):
    from api.ingestion import reset_qc_resolutions

    reset_qc_resolutions()
    eid = "t2:E00042:2025-06"
    r = client.post(
        f"/api/ingestion/2025/exceptions/{eid}/resolve",
        json={"resolution": "accept", "note": "reviewed", "reviewer": "Tester"},
    )
    assert r.status_code == 200
    assert r.json()["resolution"]["resolution"] == "accept"

    # reopen clears the stored resolution.
    r2 = client.post(
        f"/api/ingestion/2025/exceptions/{eid}/resolve", json={"resolution": "reopen"}
    )
    assert r2.status_code == 200
    assert r2.json()["resolution"] is None
    reset_qc_resolutions()


def test_ingestion_bad_resolution_rejected(client):
    r = client.post(
        "/api/ingestion/2025/exceptions/x/resolve", json={"resolution": "nonsense"}
    )
    assert r.status_code == 422


def test_ingestion_rows_browser_search_and_page(client):
    r = client.get("/api/ingestion/2025/rows?state=GA&limit=10&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    assert len(body["rows"]) <= 10
    assert "Employee_ID" in body["rows"][0]
    # Search narrows the set.
    r2 = client.get("/api/ingestion/2025/rows?state=GA&q=E00200")
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["total"] >= 1
    assert all("E00200" in row["Employee_ID"] for row in b2["rows"])


def test_ingestion_rows_sort_the_whole_list_before_paging(client):
    """29 Sep: every table sorts. The browser holds one page of 25, so the
    order is decided here, over every row, before the page is cut."""
    desc = client.get("/api/ingestion/2025/rows?state=GA&limit=5&sort=hours&order=desc").json()
    asc = client.get("/api/ingestion/2025/rows?state=GA&limit=5&sort=hours&order=asc").json()
    hours = [float(r["Hours_Worked"]) for r in desc["rows"]]
    assert hours == sorted(hours, reverse=True)
    assert desc["sort"] == "hours" and desc["order"] == "desc"
    assert float(desc["rows"][0]["Hours_Worked"]) >= float(asc["rows"][-1]["Hours_Worked"])
    # An unknown column falls back to the default order rather than erroring.
    fallback = client.get("/api/ingestion/2025/rows?state=GA&limit=5&sort=nope").json()
    assert fallback["sort"] == "employee"


def test_qc_assign_corrects_the_engine(client):
    """Resolving a test-of-twos (assign the head to one unit) removes the
    double-count, so the One/Zero average headcount drops."""
    from api.ingestion import reset_qc_resolutions

    reset_qc_resolutions()

    def ga_avg():
        return client.get("/api/onezero/2025?state=GA").json()["results"][0]["average_headcount"]

    before = ga_avg()
    r = client.post(
        "/api/ingestion/2025/exceptions/t2:E00200:2025-02/resolve",
        json={"resolution": "assign", "keep_worksite": "GA_MAC_OPS"},
    )
    assert r.status_code == 200
    client.post(
        "/api/ingestion/2025/exceptions/t2:E00200:2025-12/resolve",
        json={"resolution": "assign", "keep_worksite": "GA_ATL_HQ"},
    )
    after = ga_avg()
    assert after < before  # double-count reassigned away → aggregate corrects down

    # The exception still lists, now marked resolved.
    exc = client.get("/api/ingestion/2025?state=GA").json()["qc"]["exceptions"]
    e = next(x for x in exc if x["exception_id"] == "t2:E00200:2025-02")
    assert e["resolution"]["resolution"] == "assign"
    assert e["resolution"]["keep_worksite"] == "GA_MAC_OPS"

    reset_qc_resolutions()


# --- One exception per payroll LINE ------------------------------------------
#
# A scraggly exception was keyed (employee, worksite, pay_date). Several lines
# share that triple - reversals and pay-code splits paid the same day - so on
# the reference client 7,365 exceptions collapsed onto 3,367 ids: React warned
# 4,965 times on one page, resolving one row resolved its siblings, and a
# `drop` removed every line paid that day, including wages nobody flagged.

def _line(**over):
    row = {
        "Employee_ID": "E1", "Worksite_ID": "GA_X", "Tax_Year": 2025,
        "Pay_Period_Start": "2025-03-01", "Pay_Period_End": "2025-03-07",
        "Pay_Date": "2025-03-10", "Pay_Code": "REG",
        "Hours_Worked": 40.0, "Gross_Wages": 800.0,
    }
    row.update(over)
    return row


def test_every_exception_id_is_unique(client):
    exc = client.get("/api/ingestion/2025?state=GA").json()["qc"]["exceptions"]
    ids = [e["exception_id"] for e in exc]
    assert len(ids) == len(set(ids))


def test_a_scraggly_id_carries_no_employee_id():
    # The id travels in the resolve URL's PATH, where an employee id must not go.
    from api.ingestion import _exception_id
    from tools.qc import detect_scraggly_pay_periods

    [anomaly] = detect_scraggly_pay_periods(
        [_line(Employee_ID="102400664", Gross_Wages=-0.24, Hours_Worked=0.0)], tax_year=2025, state="GA",
    )
    eid = _exception_id(anomaly)
    assert eid.startswith("pp:")
    assert "102400664" not in eid


def test_lines_sharing_a_pay_date_get_distinct_keys():
    from tools.qc import pay_line_keys

    same_day = [_line(), _line(Gross_Wages=-0.24, Hours_Worked=0.0), _line(Pay_Code="BONUS")]
    assert len(set(pay_line_keys(same_day))) == 3


def test_exact_duplicate_lines_are_still_told_apart():
    from tools.qc import pay_line_keys

    keys = pay_line_keys([_line(), _line()])
    assert keys[0] != keys[1]
    assert keys[0].split(".")[0] == keys[1].split(".")[0]


def test_a_line_key_does_not_depend_on_read_order():
    from tools.qc import pay_line_keys

    a, b = _line(), _line(Gross_Wages=-0.24)
    forward = dict(zip(("a", "b"), pay_line_keys([a, b])))
    backward = dict(zip(("b", "a"), pay_line_keys([b, a])))
    assert forward == backward


def test_dropping_one_line_keeps_the_real_wages_paid_the_same_day():
    from api.ingestion import _QC_RESOLUTIONS, apply_calc_drops, reset_qc_resolutions
    from tools.qc import pay_line_keys

    real, stray = _line(), _line(Gross_Wages=-0.24, Hours_Worked=0.0)
    rows = [real, stray]
    reset_qc_resolutions()
    _QC_RESOLUTIONS[f"pp:{pay_line_keys(rows)[1]}"] = {"resolution": "drop"}
    try:
        assert apply_calc_drops(rows) == [real]
    finally:
        reset_qc_resolutions()


def test_dropping_one_of_two_identical_lines_keeps_the_other():
    from api.ingestion import _QC_RESOLUTIONS, apply_calc_drops, reset_qc_resolutions
    from tools.qc import pay_line_keys

    rows = [_line(Gross_Wages=-0.24), _line(Gross_Wages=-0.24)]
    reset_qc_resolutions()
    _QC_RESOLUTIONS[f"pp:{pay_line_keys(rows)[0]}"] = {"resolution": "drop"}
    try:
        assert len(apply_calc_drops(rows)) == 1
    finally:
        reset_qc_resolutions()
