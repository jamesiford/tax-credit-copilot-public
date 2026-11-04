"""Every route RM-18 moved sends a request through the mediator, and the payroll reader raises plain errors.

The route-level behaviour (response bodies, status codes) is pinned by the existing endpoint
tests, which pass unchanged. These prove the shape of the move: a router builds a query or a
command and sends it, `application/payroll_rows` raises application errors rather than
`HTTPException`, and the router edge translates them to the codes callers have always seen.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from application import payroll_rows
from bootstrap import wiring


class RecordingMediator:
    """Stands in for the mediator and records what the router sent."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, request, principal=None):
        self.sent.append(request)
        return {"sent": type(request).__name__}


@pytest.fixture()
def client_and_mediator(monkeypatch):
    from main import app

    mediator = RecordingMediator()
    monkeypatch.setattr(wiring, "get_mediator", lambda: mediator)
    return TestClient(app), mediator


#: (method, path, body, the request type the router must send)
ROUTES = [
    ("GET", "/api/v2/portfolio?year=2023", None, "GetPortfolioPageQuery"),
    ("GET", "/api/findings/1001/f-1/history", None, "GetFindingHistoryQuery"),
    ("GET", "/api/scope", None, "GetScopeOptionsQuery"),
    ("GET", "/api/scope/client/1001", None, "GetClientScopeQuery"),
    ("GET", "/api/ingestion/2023?state=GA", None, "GetIngestionOverviewQuery"),
    ("GET", "/api/ingestion/2023/rows?state=GA&limit=5", None, "GetIngestionRowsQuery"),
    ("POST", "/api/ingestion/2023/exceptions/t2:e:2023-01/resolve", {"resolution": "flag"}, "ResolveQcExceptionCommand"),
    ("GET", "/api/onezero/2023?method=min_max", None, "GetOneZeroQuery"),
    ("GET", "/api/onezero/2023/employee/E1", None, "GetEmployeeDerivationQuery"),
    ("POST", "/api/onezero/employee/E1/review", {"status": "flagged"}, "ReviewEmployeeCommand"),
    ("GET", "/api/designations/GA", None, "GetDesignationSplitsQuery"),
    ("GET", "/api/reconcile/2023", None, "GetReconciliationQuery"),
    ("GET", "/api/qc/2023", None, "GetQcExceptionReportQuery"),
]


@pytest.mark.parametrize("method,path,body,request_type", ROUTES, ids=[r[3] for r in ROUTES])
def test_a_moved_route_sends_its_request_through_the_mediator(client_and_mediator, method, path, body, request_type):
    client, mediator = client_and_mediator
    response = client.request(method, path, json=body)
    assert response.status_code == 200, response.text
    assert [type(r).__name__ for r in mediator.sent] == [request_type]


def test_the_one_zero_route_names_a_bad_method_before_it_sends_anything(client_and_mediator):
    client, mediator = client_and_mediator
    response = client.get("/api/onezero/2023?method=nonsense")
    assert response.status_code == 400
    assert response.json() == {"detail": "method must be pay_period | min_max | both"}
    assert mediator.sent == []


def test_a_review_carries_the_person_who_made_it_as_the_commands_actor(client_and_mediator):
    client, mediator = client_and_mediator
    client.post("/api/onezero/employee/E1/review", json={"status": "validated", "reviewer": "Pat"})
    (command,) = mediator.sent
    assert command.actor == "Pat" and command.employee_id == "E1" and command.status == "validated"


# --- the payroll reader raises application errors, the router edge translates them -----------


@pytest.fixture()
def no_payroll(monkeypatch):
    monkeypatch.setattr(payroll_rows, "load_pay_periods", lambda account_id=None: [])


def test_a_named_client_with_no_rows_is_a_typed_error_not_an_http_one(no_payroll):
    with pytest.raises(payroll_rows.NoPayrollForClient, match="No payroll for client 42"):
        payroll_rows.require_pay_periods(account_id=42)


def test_an_absent_dataset_is_a_different_typed_error(no_payroll):
    with pytest.raises(payroll_rows.PayrollDatasetNotGenerated, match="not generated"):
        payroll_rows.require_pay_periods()
    assert issubclass(payroll_rows.PayrollDatasetNotGenerated, payroll_rows.PayrollNotAvailable)
    assert not issubclass(payroll_rows.NoPayrollForClient, payroll_rows.PayrollDatasetNotGenerated)


def test_the_router_edge_maps_them_to_404_and_503(no_payroll):
    from api._payperiods import require_pay_periods

    with pytest.raises(HTTPException) as named:
        require_pay_periods(account_id=42)
    with pytest.raises(HTTPException) as absent:
        require_pay_periods()
    assert (named.value.status_code, named.value.detail) == (404, "No payroll for client 42 in the active data source.")
    assert (absent.value.status_code, absent.value.detail) == (503, payroll_rows.NOT_GENERATED_DETAIL)


def test_the_payroll_reader_imports_no_web_framework():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(payroll_rows))
    modules = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not modules & {"fastapi", "starlette", "api"}


def test_qc_resolutions_flow_into_the_rows_a_calculation_loads(monkeypatch):
    from application import qc_resolutions

    rows = [
        {"Employee_ID": "E1", "Worksite_ID": "GA_A", "Pay_Date": "2023-03-10"},
        {"Employee_ID": "E1", "Worksite_ID": "GA_B", "Pay_Date": "2023-03-17"},
    ]
    monkeypatch.setattr(payroll_rows, "load_pay_periods", lambda account_id=None: list(rows))
    qc_resolutions.reset_qc_resolutions()
    try:
        qc_resolutions.QC_RESOLUTIONS["t2:E1:2023-03"] = {"resolution": "assign", "keep_worksite": "GA_A"}
        kept = payroll_rows.require_pay_periods(drop_qc=True)
        assert [r["Worksite_ID"] for r in kept] == ["GA_A"]
        assert len(payroll_rows.require_pay_periods()) == 2  # the QC detector still sees everything
    finally:
        qc_resolutions.reset_qc_resolutions()


# --- the writes are commands with an actor, and the mediator audits them ---------------------


def test_resolving_a_qc_exception_is_an_audited_command():
    from application.commands.resolve_qc_exception import ResolveQcExceptionCommand
    from application.qc_resolutions import QC_RESOLUTIONS, reset_qc_resolutions

    reset_qc_resolutions()
    mediator = wiring.build_mediator()
    try:
        result = mediator.send(ResolveQcExceptionCommand(actor="Pat", exception_id="pp:k1", resolution="drop"))
        assert result["resolution"]["reviewer"] == "Pat" and QC_RESOLUTIONS["pp:k1"]["resolution"] == "drop"
        assert [r.request for r in mediator.audit.records][-1] == "ResolveQcExceptionCommand"
        reopened = mediator.send(ResolveQcExceptionCommand(actor="Pat", exception_id="pp:k1", resolution="reopen"))
        assert reopened == {"ok": True, "exception_id": "pp:k1", "resolution": None}
        assert "pp:k1" not in QC_RESOLUTIONS
    finally:
        reset_qc_resolutions()


def test_the_assessment_is_a_pure_application_service_over_a_repository_it_is_given():
    from application.assessment import assess_client

    assert assess_client(1, [], repository=None) == {"assessed": [], "declined": [], "years": []}
