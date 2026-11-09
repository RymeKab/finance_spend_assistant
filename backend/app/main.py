"""
The web API that the frontend talks to.

Endpoints
---------
    GET  /health    is the server up, and is a Claude key configured?
    GET  /summary   overview of the invoice data (no AI involved; works without a key)
    POST /ask       answer a question, with the evidence it is based on

Run it (from the backend folder):
    uvicorn app.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs

This file only handles web concerns: routes, request IDs, CORS and turning errors
into JSON. The actual work happens in assistant.py and the modules it uses.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.assistant import SpendAssistant
from app.config import Settings, load_settings
from app.errors import AppError
from app.llm.client import create_claude_client
from app.schemas import AskRequest, AskResponse, ErrorResponse, HealthResponse, SummaryResponse

logger = logging.getLogger("spend_assistant")
ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (422, 500, 502, 503, 504)}


def create_app(settings: Settings | None = None, client_factory: Callable[[Settings], Any] | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings and a fake Claude client factory."""
    settings = settings or load_settings()
    assistant = SpendAssistant(settings, client_factory or create_claude_client)

    app = FastAPI(
        title="Finance Spend Intelligence Assistant",
        version="1.0.0",
        description="Answers questions about 2025 invoices and the procurement policy, with the evidence behind each answer.",
    )
    app.state.assistant = assistant

    # -------------------------------------------------------------------- errors
    def error_json(request: Request, status: int, code: str, message: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": message, "request_id": request_id}},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning("%s: %s", exc.code, exc.message)
        return error_json(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return error_json(request, 422, "invalid_question", "Please enter a question between 1 and 1,000 characters.")

    # ---------------------------------------------------- request IDs + crash safety net
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        # Every request gets an ID. It appears in the response, the audit log and any error,
        # so a user's report can be matched to the exact log line.
        request.state.request_id = uuid.uuid4().hex[:12]
        try:
            response = await call_next(request)
        except Exception:
            # Anything unexpected still returns the standard error shape (and, because the
            # CORS middleware below wraps this one, the browser can read it).
            logger.exception("Unexpected error")
            response = error_json(request, 500, "internal_error", "Something went wrong on the server. Please try again.")
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    # Added last so it is the outermost layer: every response, errors included, gets CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # -------------------------------------------------------------------- routes
    # /health and /summary only return precomputed data, so they run directly on the
    # event loop and stay fast even while slow questions are being answered.
    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict:
        return assistant.health()

    @app.get("/summary", response_model=SummaryResponse, responses=ERROR_RESPONSES)
    async def summary() -> dict:
        return assistant.summary()

    # A plain `def` (not `async def`): FastAPI runs it in a worker thread, so a slow
    # Claude call never blocks other requests.
    @app.post("/ask", response_model=AskResponse, responses=ERROR_RESPONSES)
    def ask(body: AskRequest, request: Request) -> dict:
        return assistant.ask(body.question, request.state.request_id)

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
