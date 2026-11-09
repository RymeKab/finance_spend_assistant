"""
The HTTP layer: routes, status codes, the error shape and request IDs.

Needs FastAPI and httpx (both in requirements.txt). These tests are skipped
automatically if they aren't installed.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import FakeClaude, FailingClaude, submit, tool_use  # noqa: E402


def client_with(settings, fake=None) -> TestClient:
    factory = (lambda _s: fake) if fake is not None else None
    return TestClient(create_app(settings, factory))


def test_health(settings):
    response = client_with(settings).get("/health")
    assert response.status_code == 200
    assert response.json()["llm_configured"] is True
    assert response.headers["X-Request-ID"]


def test_summary(settings):
    body = client_with(settings).get("/summary").json()
    assert body["invoice_count"] == 140
    assert {"gross", "credit_notes", "net"} <= set(body["spend_eur"])


def test_ask_returns_answer_and_evidence(settings):
    fake = FakeClaude([
        [tool_use("query_spend", {"filters": {"countries": ["Spain"]}})],
        [submit(status="answered", answer="Spend with Spanish vendors is in the evidence.", data_refs=["q1"])],
    ])
    response = client_with(settings, fake).post("/ask", json={"question": "Total spend with vendors in Spain?"})
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["route"] == ["data"] and body["evidence"]["data"][0]["invoice_count"] == 49


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
def test_invalid_question_is_422(settings, question):
    response = client_with(settings).post("/ask", json={"question": question})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_question"


def test_missing_key_is_503_and_summary_still_works(tmp_path):
    client = TestClient(create_app(Settings(key_1=None, log_dir=tmp_path)))
    response = client.post("/ask", json={"question": "Top vendors?"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "llm_not_configured" and error["request_id"]
    assert client.get("/summary").status_code == 200


def test_timeout_is_504(settings):
    anthropic = pytest.importorskip("anthropic")
    import httpx

    fake = FailingClaude(anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com")))
    response = client_with(settings, fake).post("/ask", json={"question": "Top vendors?"})
    assert response.status_code == 504 and response.json()["error"]["code"] == "llm_timeout"


def test_a_failing_claude_client_never_leaks_details(settings):
    fake = FailingClaude(RuntimeError("secret internal detail"))
    response = client_with(settings, fake).post("/ask", json={"question": "Top vendors?"})
    assert response.status_code == 500
    assert "secret internal detail" not in response.text


def test_crash_returns_500_in_the_standard_shape_with_cors(settings, monkeypatch):
    app = create_app(settings)
    monkeypatch.setattr(app.state.assistant, "ask", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug")))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/ask", json={"question": "Top vendors?"}, headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]
