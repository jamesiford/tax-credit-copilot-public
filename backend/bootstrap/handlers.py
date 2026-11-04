"""Every request-to-handler binding: what happens when this request arrives?

Explicit rather than auto-discovered. Decorator registration scattered across modules is
less typing and much harder to answer "what happens when this request arrives?" from; you
have to find the handler before you can read it. Here the whole dispatch table is one
screen. `bootstrap.wiring.build_mediator` calls `register_handlers` on the mediator it
builds, so the dispatch table and the collaborators it uses are composed in one root.
"""
from __future__ import annotations

from application.ai.handlers import handle_channel_narration, handle_narrate_brief, handle_route_question
from application.ai.requests import ChannelNarrationQuery, NarrateBriefQuery, RouteQuestionQuery
from application.commands.assess_client import AssessClientCommand, handle_assess_client
from application.commands.create_claim_package import CreateClaimPackageCommand, handle_create_claim_package
from application.commands.record_claim import RecordClaimCommand, handle_record_claim
from application.commands.resolve_finding import (
    ReopenFindingCommand,
    ResolveFindingCommand,
    handle_reopen_finding,
    handle_resolve_finding,
)
from application.commands.resolve_qc_exception import ResolveQcExceptionCommand, handle_resolve_qc_exception
from application.commands.review_employee import ReviewEmployeeCommand, handle_review_employee
from application.commands.run_client_calculation import (
    RunClientCalculationCommand,
    handle_run_client_calculation,
)
from application.commands.set_base_year import SetBaseYearCommand, handle_set_base_year
from application.commands.set_engagement import SetEngagementCommand, handle_set_engagement
from application.commands.transition_claim import TransitionClaimCommand, handle_transition_claim
from application.mediator import Mediator
from application.queries.get_channel_audit import GetChannelAuditQuery, handle_get_channel_audit
from application.queries.get_client_situation import GetClientSituationQuery, handle_get_client_situation
from application.queries.get_coverage import (
    GetCellHistoryQuery,
    GetClientCoverageQuery,
    GetPortfolioCoverageQuery,
    handle_get_cell_history,
    handle_get_client_coverage,
    handle_get_portfolio_coverage,
)
from application.queries.get_designation_splits import GetDesignationSplitsQuery, handle_get_designation_splits
from application.queries.get_eligibility import GetEligibilityQuery, handle_get_eligibility
from application.queries.get_employee_derivation import (
    GetEmployeeDerivationQuery,
    handle_get_employee_derivation,
)
from application.queries.get_employee_drill import GetEmployeeDrillQuery, handle_get_employee_drill
from application.queries.get_finding_history import GetFindingHistoryQuery, handle_get_finding_history
from application.queries.get_in_year_progress import GetInYearProgressQuery, handle_get_in_year_progress
from application.queries.get_ingestion_overview import GetIngestionOverviewQuery, handle_get_ingestion_overview
from application.queries.get_ingestion_rows import GetIngestionRowsQuery, handle_get_ingestion_rows
from application.queries.get_one_zero import GetOneZeroQuery, handle_get_one_zero
from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery, handle_get_onezero_matrix
from application.queries.get_portfolio_page import GetPortfolioPageQuery, handle_get_portfolio_page
from application.queries.get_proximity import GetProximityQuery, handle_get_proximity
from application.queries.get_qc_exception_report import GetQcExceptionReportQuery, handle_get_qc_exception_report
from application.queries.get_reconciliation import GetReconciliationQuery, handle_get_reconciliation
from application.queries.get_scope import (
    GetClientScopeQuery,
    GetScopeOptionsQuery,
    handle_get_client_scope,
    handle_get_scope_options,
)
from application.queries.get_unit_trend import GetUnitTrendQuery, handle_get_unit_trend
from application.queries.list_findings import ListFindingsQuery, handle_list_findings
from application.queries.rebase_unit import RebaseUnitQuery, handle_rebase_unit
from application.queries.simulate_employee import SimulateEmployeeQuery, handle_simulate_employee
from application.queries.simulate_portfolio import SimulatePortfolioQuery, handle_simulate_portfolio
from application.queries.simulate_unit import SimulateUnitQuery, handle_simulate_unit

def _register_queries(mediator: Mediator) -> None:
    """Queries: compute and return, change nothing."""
    mediator.register(GetProximityQuery, handle_get_proximity)
    mediator.register(GetEligibilityQuery, handle_get_eligibility)
    mediator.register(GetOneZeroMatrixQuery, handle_get_onezero_matrix)
    mediator.register(GetOneZeroQuery, handle_get_one_zero)
    mediator.register(GetEmployeeDerivationQuery, handle_get_employee_derivation)
    mediator.register(GetDesignationSplitsQuery, handle_get_designation_splits)
    mediator.register(GetReconciliationQuery, handle_get_reconciliation)
    mediator.register(GetQcExceptionReportQuery, handle_get_qc_exception_report)
    mediator.register(GetIngestionOverviewQuery, handle_get_ingestion_overview)
    mediator.register(GetIngestionRowsQuery, handle_get_ingestion_rows)
    mediator.register(GetScopeOptionsQuery, handle_get_scope_options)
    mediator.register(GetClientScopeQuery, handle_get_client_scope)
    mediator.register(GetUnitTrendQuery, handle_get_unit_trend)
    mediator.register(GetEmployeeDrillQuery, handle_get_employee_drill)
    mediator.register(GetClientCoverageQuery, handle_get_client_coverage)
    mediator.register(GetPortfolioCoverageQuery, handle_get_portfolio_coverage)
    mediator.register(GetPortfolioPageQuery, handle_get_portfolio_page)
    mediator.register(GetCellHistoryQuery, handle_get_cell_history)
    mediator.register(SimulatePortfolioQuery, handle_simulate_portfolio)
    mediator.register(SimulateUnitQuery, handle_simulate_unit)
    mediator.register(SimulateEmployeeQuery, handle_simulate_employee)
    mediator.register(RebaseUnitQuery, handle_rebase_unit)
    mediator.register(GetInYearProgressQuery, handle_get_in_year_progress)
    mediator.register(GetClientSituationQuery, handle_get_client_situation)
    mediator.register(ListFindingsQuery, handle_list_findings)
    mediator.register(GetFindingHistoryQuery, handle_get_finding_history)
    mediator.register(GetChannelAuditQuery, handle_get_channel_audit)


def _register_streaming_queries(mediator: Mediator) -> None:
    """Streaming queries: model narration, through the same pipeline."""
    mediator.register(NarrateBriefQuery, handle_narrate_brief)
    mediator.register(RouteQuestionQuery, handle_route_question)
    mediator.register(ChannelNarrationQuery, handle_channel_narration)


def _register_commands(mediator: Mediator) -> None:
    """Commands: change what the business believes."""
    mediator.register(AssessClientCommand, handle_assess_client)
    mediator.register(ResolveFindingCommand, handle_resolve_finding)
    mediator.register(ReopenFindingCommand, handle_reopen_finding)
    mediator.register(ResolveQcExceptionCommand, handle_resolve_qc_exception)
    mediator.register(ReviewEmployeeCommand, handle_review_employee)
    mediator.register(RunClientCalculationCommand, handle_run_client_calculation)
    mediator.register(SetBaseYearCommand, handle_set_base_year)
    mediator.register(RecordClaimCommand, handle_record_claim)
    mediator.register(TransitionClaimCommand, handle_transition_claim)
    mediator.register(SetEngagementCommand, handle_set_engagement)
    mediator.register(CreateClaimPackageCommand, handle_create_claim_package)


def register_handlers(mediator: Mediator) -> Mediator:
    """Bind every request type to its handler.

    Each handler is looked up in this module's namespace when the mediator is built, so
    a test can replace one (`monkeypatch.setattr(handlers, "handle_x", ...)`) and rebuild.
    """
    _register_queries(mediator)
    _register_streaming_queries(mediator)
    _register_commands(mediator)
    return mediator
