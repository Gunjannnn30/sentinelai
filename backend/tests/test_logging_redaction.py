"""Request logging must never include bodies, cookies, or credentials.

The structured request line logs method, path, status, duration and request
id only (see ``app.main.RequestContextMiddleware``); this test pins that
contract so a future "helpful" extra field cannot leak a payload.
"""
import json

from fastapi.testclient import TestClient

from .conftest import auth_headers

SECRET_PROMPT = "TopSecret-Content-8f3b " * 3


def test_request_logs_omit_credentials_and_bodies(fresh: TestClient, caplog) -> None:
    with caplog.at_level("INFO"):
        reg = fresh.post(
            "/api/v1/auth/register",
            json={
                "email": "log-redact@example.com",
                "password": "Log-Redact-Pw-77!",
                "org_name": "Log Redact Org",
                "full_name": "Log Redactor",
            },
        )
        assert reg.status_code == 201, reg.text
        chat = fresh.post(
            "/api/v1/chat/completions",
            json={"messages": [{"role": "user", "content": SECRET_PROMPT}]},
            headers=auth_headers({"csrf": fresh.cookies.get("sentinel_csrf", "")}),
        )
        assert chat.status_code == 200, chat.text

    records = [rec for rec in caplog.records if rec.name == "main"]

    # The request line is ``log.info("request", extra={...})``: method/path/status
    # live in the structured extras (rendered onto the JSON line), while
    # ``getMessage()`` returns only the bare "request". This logging setup nests
    # them under ``rec.__dict__["extra_fields"]``, so read them there.
    def _extras(rec):
        flat = {
            k: v
            for k, v in rec.__dict__.items()
            if k
            not in (
                "msg", "args", "name", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "stack_info",
                "message", "extra_fields",
            )
        }
        flat.update(rec.__dict__.get("extra_fields", {}))
        return flat

    request_recs = [(rec, _extras(rec)) for rec in records]
    request_recs = [(rec, ex) for rec, ex in request_recs if "path" in ex]
    assert request_recs, [rec.getMessage() for rec in records]
    assert any(ex.get("method") == "POST" for _, ex in request_recs)
    assert any(ex.get("path") == "/api/v1/chat/completions" for _, ex in request_recs)

    # Render every record the way the JSON formatter would (message + extras),
    # so the negative assertions below also cover the structured fields — a
    # leaked secret would most likely arrive as an extra, not in the bare message.
    lines = [
        json.dumps({"message": rec.getMessage(), **_extras(rec)}, default=str)
        for rec in records
    ]
    joined = "\n".join(lines)

    # no secrets, no payloads, no cookie material
    assert "Log-Redact-Pw-77!" not in joined
    assert "log-redact@example.com" not in joined
    assert "TopSecret-Content-8f3b" not in joined
    assert "sentinel_session" not in joined
    assert "X-CSRF-Token" not in joined
