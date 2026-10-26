"""Liveness / readiness / metrics endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import HealthOut, ReadyOut

router = APIRouter(tags=["ops"])

_START = time.time()
_REQUESTS_TOTAL = 0


def bump_requests() -> None:
    global _REQUESTS_TOTAL
    _REQUESTS_TOTAL += 1


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness: process is up. No dependency checks (doesn't flap on DB blips)."""
    return HealthOut(status="ok", env=settings.app_env)


@router.get("/ready", response_model=ReadyOut)
def ready(response: Response, db: Session = Depends(get_db)) -> ReadyOut:
    """Readiness: database reachable + configuration sane."""
    checks: dict = {}
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        checks["database_error"] = type(exc).__name__  # no secrets in error names
        response.status_code = 503

    problems = settings.missing_required()
    if problems:
        checks["config_problems"] = problems
        response.status_code = 503

    checks["providers_configured"] = settings.provider_keys()
    checks["uptime_seconds"] = int(time.time() - _START)
    status = "ok" if response.status_code != 503 else "degraded"
    return ReadyOut(status=status, database=db_status, checks=checks)


@router.get("/metrics", tags=["ops"])
def metrics() -> Response:
    """Basic Prometheus-style text metrics (single process counters)."""
    body = (
        "# HELP sentinelai_requests_total Gateway requests handled since boot.\n"
        "# TYPE sentinelai_requests_total counter\n"
        f"sentinelai_requests_total {_REQUESTS_TOTAL}\n"
        "# HELP sentinelai_uptime_seconds Process uptime.\n"
        "# TYPE sentinelai_uptime_seconds gauge\n"
        f"sentinelai_uptime_seconds {int(time.time() - _START)}\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")
