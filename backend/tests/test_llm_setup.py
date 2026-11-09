"""The Claude-facing definitions: tool schemas, the strict final-answer tool, error mapping."""

import json

import pytest
from pydantic import BaseModel

from app.errors import AppError, LLMTimeout, LLMUnavailable
from app.llm.submission import SUBMIT_ANSWER_TOOL, AnswerSubmission
from app.tools import json_schema_for


def test_submit_answer_is_strict_and_simple():
    schema = SUBMIT_ANSWER_TOOL["input_schema"]
    assert SUBMIT_ANSWER_TOOL["strict"] is True
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"]) == set(AnswerSubmission.model_fields)
    # Keywords strict tools don't support must not appear.
    text = json.dumps(schema)
    for keyword in ("minLength", "maxLength", "default", "anyOf", "$ref"):
        assert keyword not in text


def test_schema_generation_keeps_a_field_called_title():
    class Example(BaseModel):
        title: str
        count: int = 0

    schema = json_schema_for(Example)
    assert set(schema["properties"]) == {"title", "count"}
    assert "title" not in schema["properties"]["title"]  # the keyword is still removed


def test_sdk_errors_become_typed_api_errors():
    anthropic = pytest.importorskip("anthropic")
    import httpx

    from app.llm.client import translate_llm_error

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def status_error(cls, code):
        return cls("message", response=httpx.Response(code, request=request), body=None)

    assert isinstance(translate_llm_error(anthropic.APITimeoutError(request=request)), LLMTimeout)
    assert isinstance(translate_llm_error(anthropic.APIConnectionError(request=request)), LLMUnavailable)
    unknown_model = translate_llm_error(status_error(anthropic.NotFoundError, 404))
    assert isinstance(unknown_model, LLMUnavailable) and "ANTHROPIC_MODEL" in unknown_model.message
    bad_key = translate_llm_error(status_error(anthropic.AuthenticationError, 401))
    assert "key_1" in bad_key.message
    other = translate_llm_error(RuntimeError("internal detail"))
    assert type(other) is AppError and other.status_code == 500 and "internal detail" not in other.message
