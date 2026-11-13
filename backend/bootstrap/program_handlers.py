"""The program draft and catalog handlers, bound to their requests. [F05]

Kept beside `handlers.py` rather than in it: that module is the dispatch table for the engine's own requests and sits at the
size standard. `register_handlers` calls `register_program_handlers`, so the one table is still composed in one root.
"""
from __future__ import annotations

from application.commands.create_program_draft import CreateProgramDraftCommand, handle_create_program_draft
from application.commands.edit_program_draft import EditProgramDraftCommand, handle_edit_program_draft
from application.commands.request_program_review import RequestProgramReviewCommand, handle_request_program_review
from application.commands.review_program_draft import ReviewProgramDraftCommand, handle_review_program_draft
from application.commands.validate_program_draft import ValidateProgramDraftCommand, handle_validate_program_draft
from application.commands.withdraw_program_draft import WithdrawProgramDraftCommand, handle_withdraw_program_draft
from application.mediator import Mediator
from application.queries.program_catalog_reads import (
    GetProgramDetailQuery, ListProgramCatalogQuery, handle_get_program_detail, handle_list_program_catalog,
)
from application.queries.program_draft_reads import (
    GetProgramDraftQuery, ListProgramDraftsQuery, handle_get_program_draft, handle_list_program_drafts,
)
from application.queries.preview_program_draft import PreviewProgramDraftQuery, handle_preview_program_draft
from bootstrap import program_draft_wiring  # noqa: F401 - binds the draft repository for the draft handlers


def register_program_handlers(mediator: Mediator) -> Mediator:
    mediator.register(ListProgramCatalogQuery, handle_list_program_catalog)
    mediator.register(GetProgramDetailQuery, handle_get_program_detail)
    mediator.register(ListProgramDraftsQuery, handle_list_program_drafts)
    mediator.register(GetProgramDraftQuery, handle_get_program_draft)
    mediator.register(PreviewProgramDraftQuery, handle_preview_program_draft)
    for request, handler in (
        (CreateProgramDraftCommand, handle_create_program_draft), (EditProgramDraftCommand, handle_edit_program_draft),
        (ValidateProgramDraftCommand, handle_validate_program_draft), (RequestProgramReviewCommand, handle_request_program_review),
        (ReviewProgramDraftCommand, handle_review_program_draft), (WithdrawProgramDraftCommand, handle_withdraw_program_draft),
    ):
        mediator.register(request, handler)
    return mediator
