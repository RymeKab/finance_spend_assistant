"""
The errors the API can return, each with its HTTP status code.

Every error reaches the frontend in the same shape:

    {"error": {"code": "llm_timeout", "message": "...", "request_id": "..."}}

The frontend turns each `code` into a plain-language message.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class: an error we expected and can explain to the user."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class LLMNotConfigured(AppError):
    """No Claude API key (key_1) is set, so questions can't be answered."""

    status_code = 503
    code = "llm_not_configured"


class LLMUnavailable(AppError):
    """Claude could not be reached, rejected the key, or is overloaded."""

    status_code = 503
    code = "llm_unavailable"


class LLMTimeout(AppError):
    """Claude took longer than the configured timeout."""

    status_code = 504
    code = "llm_timeout"


class LLMBadOutput(AppError):
    """Claude's reply could not be used, even after one corrective retry."""

    status_code = 502
    code = "llm_bad_output"
