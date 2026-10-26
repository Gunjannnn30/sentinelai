#!/usr/bin/env python
"""SentinelAI smoke test against a RUNNING backend.

    python scripts/smoke.py                       # http://127.0.0.1:8123
    SENTINEL_API_BASE=http://localhost:8123 python scripts/smoke.py

Checks (each prints PASS/FAIL, exit code 1 on any failure):
  1. GET  /health
  2. POST /api/v1/auth/register        (fresh org every run)
  3. GET  /api/v1/models
  4. POST /api/v1/chat/completions     -> success (mock provider, labeled demo)
  5. POST /api/v1/chat/completions     -> blocked (credential-shaped prompt)
  6. GET  /api/v1/admin/audit/verify   -> chain intact

Cookie/CSRF: unsafe methods from an authenticated cookie client must send
X-CSRF-Token (double-submit) — handled here exactly like the frontend does.
"""
from __future__ import annotations

import os
import sys
import uuid

import httpx

BASE = os.environ.get("SENTINEL_API_BASE", "http://127.0.0.1:8123").rstrip("/")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=30.0, follow_redirects=False) as c:
        # 1. health -------------------------------------------------------
        r = c.get("/health")
        if not record("GET /health", r.status_code == 200, f"{r.status_code}"):
            return 1  # server not up; everything else would be noise

        # 2. register -----------------------------------------------------
        email = f"smoke-{uuid.uuid4().hex[:12]}@example.com"
        r = c.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "Smoke-Test-Pw-1!",
                "org_name": f"Smoke {uuid.uuid4().hex[:6]}",
                "full_name": "Smoke Test",
            },
        )
        csrf = c.cookies.get("sentinel_csrf", "")
        if not record("POST /auth/register", r.status_code == 201,
                      f"{r.status_code} {r.text[:160]}"):
            return 1

        hdr = {"X-CSRF-Token": csrf} if csrf else {}

        # 3. models -------------------------------------------------------
        r = c.get("/api/v1/models")
        models = r.json() if r.status_code == 200 else []
        record("GET /models", r.status_code == 200 and bool(models),
               f"{len(models) if isinstance(models, list) else '?'} models")

        # 4. success chat (mock provider -> demo-labeled content) ---------
        r = c.post(
            "/api/v1/chat/completions",
            headers=hdr,
            json={"messages": [{"role": "user", "content": "Say hello in one short sentence."}]},
        )
        body = r.json() if r.status_code == 200 else {}
        record(
            "POST /chat/completions (success)",
            r.status_code == 200 and body.get("status") == "success"
            and body.get("demo") is True,
            f"status={body.get('status')} demo={body.get('demo')}",
        )

        # 5. guardrail block (credential-shaped prompt) -------------------
        r = c.post(
            "/api/v1/chat/completions",
            headers=hdr,
            json={"messages": [{"role": "user",
                                "content": "Use this API key: sk-abcdef1234567890ABCDEF1234567890"}]},
        )
        body = r.json() if r.status_code == 200 else {}
        record(
            "POST /chat/completions (blocked)",
            body.get("status") == "blocked" and body.get("policy_outcome") == "block",
            f"outcome={body.get('policy_outcome')} findings={len(body.get('findings') or [])}",
        )

        # 6. audit chain --------------------------------------------------
        r = c.get("/api/v1/admin/audit/verify")
        body = r.json() if r.status_code == 200 else {}
        record("GET /admin/audit/verify", body.get("ok") is True,
               f"checked={body.get('checked')}")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
