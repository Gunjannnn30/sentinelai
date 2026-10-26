"""Shared fixtures.

Env is pinned before any app import (config reads env at import time). The
register/login rate limiter is effectively disabled here so that unrelated
tests never trip it; throttling itself is asserted in test_auth_rate_limit.
"""

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

# The `ai` package lives at the repo root, one level above `backend/`.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ["SENTINEL_APP_ENV"] = "test"
os.environ["SENTINEL_DATABASE_URL"] = "sqlite:///" + tempfile.mkdtemp(
    prefix="sentinelai-test-"
) + "/test.db"
os.environ["SENTINEL_SESSION_COOKIE_SECURE"] = "false"
os.environ["SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["SENTINEL_SEED_DEMO_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal, engine
from app.main import app
from app.services import ratelimit
from app.services.seed import seed_demo_if_empty

from .helpers import chat_body


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create the schema and seed demo data once per test session."""
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_if_empty(db)
        db.commit()
    yield
    engine.dispose()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """Session client: lifespan (and therefore app state) runs exactly once.

    Its cookie jar is shared by every test using it directly, so tests that
    need an independent identity use the ``fresh`` fixture instead.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh() -> Iterator[TestClient]:
    """A brand new client per test: empty cookie jar, app state already up."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_state(client: TestClient) -> Iterator[None]:
    """Reset per-test mutable state around every test."""
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture(scope="session")
def session(client: TestClient) -> dict[str, str]:
    """Logged-in identity shared by the tests that use the session ``client``.

    Registration happens on a throwaway client so the shared cookie jar only
    ever holds the login session established here.
    """
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    creds = {
        "email": f"dev-{suffix}@sentinelai.dev",
        "password": "dev-password-123",
        "org_name": f"Dev Org {suffix}",
    }
    with TestClient(app) as own:
        resp = own.post("/api/v1/auth/register", json=creds)
        assert resp.status_code == 201, resp.text
        data = resp.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200
    return {
        "email": creds["email"],
        "password": creds["password"],
        "org_name": creds["org_name"],
        "org_id": data["org"]["id"],
        "user_id": data["user"]["id"],
        "csrf": token,
    }


def auth_headers(session: dict[str, str]) -> dict[str, str]:
    return {"X-CSRF-Token": session["csrf"]}


def chat(
    client: TestClient,
    session: dict[str, str],
    content: str = "Say hello",
    **overrides: object,
) -> dict:
    """POST a chat completion and return the parsed body (any status)."""
    resp = client.post(
        "/api/v1/chat/completions",
        json=chat_body(content, **overrides),
        headers=auth_headers(session),
    )
    return resp.json()
