"""Error handlers for typed errors that mean the same HTTP status wherever they are raised. [F04c.2]"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from application.program_defaults import ProgramStateConflict


def install(app: FastAPI) -> None:
    """Register the handlers on the app."""

    @app.exception_handler(ProgramStateConflict)
    async def _program_state_conflict(_request: Request, exc: ProgramStateConflict) -> JSONResponse:
        """A request naming a program and a different state is the caller's to fix: a 422."""
        return JSONResponse(status_code=422, content={"detail": str(exc)})
