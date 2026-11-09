"""
Creates the Claude client from the API key `key_1`, and translates Claude's
errors into the app's own errors (see errors.py).

The Anthropic SDK is imported only when it's needed. The data tools, the summary
and the unit tests therefore run even on a machine without the SDK installed.

Error messages shown to users are fixed, plain sentences. The technical details
go to the server log, never to the browser.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.errors import AppError, LLMNotConfigured, LLMTimeout, LLMUnavailable

logger = logging.getLogger("spend_assistant")


def create_claude_client(settings: Settings) -> Any:
    """Return an Anthropic client, or raise a clear error if it can't be created."""
    if not settings.key_1:
        raise LLMNotConfigured(
            "No Claude API key is configured, so questions can't be answered. "
            "Add key_1=<your key> to backend/.env and restart the backend. The summary still works."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - only without dependencies installed
        raise LLMUnavailable("The 'anthropic' package is not installed. Run: pip install -r requirements.txt") from exc

    # The SDK retries temporary failures (connection problems, timeouts, rate limits,
    # overload) by itself. One retry keeps the total wait predictable; the orchestrator
    # also enforces an overall deadline per question.
    return anthropic.Anthropic(api_key=settings.key_1, timeout=settings.llm_timeout_seconds, max_retries=1)


def translate_llm_error(exc: Exception) -> AppError:
    """Map an exception raised while calling Claude to one of our API errors."""
    if isinstance(exc, AppError):
        return exc
    logger.warning("Claude call failed: %r", exc)  # full details for the server log only
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return AppError("Unexpected problem while calling Claude.")

    # Order matters: a timeout is a special kind of connection error.
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMTimeout("Claude took too long to answer. Please try again.")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMUnavailable("Claude could not be reached (network problem). Please try again.")
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return LLMUnavailable("The Claude API key (key_1) was rejected. Check backend/.env.")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMUnavailable("Claude is rate-limiting requests right now. Please wait a moment and retry.")
    if isinstance(exc, (anthropic.BadRequestError, anthropic.NotFoundError)):
        # Most often an unknown or unavailable model, or a setting the model doesn't accept.
        return LLMUnavailable(
            "Claude rejected the request. Check ANTHROPIC_MODEL (and LLM_EFFORT / LLM_TEMPERATURE) in "
            "backend/.env; details are in the server log."
        )
    if isinstance(exc, anthropic.APIStatusError):
        return LLMUnavailable(f"Claude returned an error ({exc.status_code}). Please try again.")
    return AppError("Unexpected problem while calling Claude.")
