"""SentinelAI FastAPI application factory.

Responsibilities wired here (and nowhere else):
- structured logging + request-id middleware
- request-size guard (413 before the body is parsed)
- CSRF enforcement for cookie-authenticated unsafe methods
- consistent error envelope (see ``app.core.errors``)
- lifespan: first-boot demo seeding + config validation
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
)
from app.core.logging import get_logger, setup_logging
from app.core.security import enforce_csrf
from app.db.session import session_scope

setup_logging(settings.log_level)
log = get_logger("main")

API_PREFIX = settings.api_v1_prefix


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, log one structured line per request, enforce CSRF."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            enforce_csrf(request)
        except AppError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.code, "message": exc.message,
                                   "details": exc.details, "request_id": request_id}},
                headers={"X-Request-ID": request_id},
            )
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "request",
            extra={"request_id": request_id, "method": request.method,
                   "path": request.url.path, "status": response.status_code,
                   "duration_ms": duration_ms},
        )
        response.headers["X-Request-ID"] = request_id
        return response


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies (413) before they are buffered/parsed."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"error": {"code": "payload_too_large",
                                       "message": f"Request body exceeds {settings.max_request_bytes} bytes.",
                                       "details": {}, "request_id": "unknown"}},
                )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.missing_required()
    if problems:
        log.error("Configuration problems detected.", extra={"problems": problems})
        if settings.is_production:
            raise RuntimeError(f"Refusing to start with invalid config: {problems}")

    if not settings.is_production:
        # Dev/test convenience: create any missing tables so a fresh clone runs
        # without a migration step. In production the schema is managed *only*
        # by Alembic (``alembic upgrade head``), so we never auto-create there.
        from app.db.base import Base
        from app.db.session import engine

        Base.metadata.create_all(bind=engine)

    if settings.seed_demo_data:
        with session_scope() as db:
            from app.services.seed import seed_demo_if_empty

            seeded = seed_demo_if_empty(db)
            if seeded:
                log.info("Seeded demo organization (clearly labelled as demo data).")

    log.info("SentinelAI API started.", extra={"env": settings.app_env})
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "AI governance & security platform. Provides a policy-enforcing "
            "LLM gateway, guardrails, routing, audit trail, analytics and "
            "evaluations across OpenAI / Anthropic / Gemini / Ollama."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    app.add_middleware(RequestSizeMiddleware)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=API_PREFIX)

    # Health/metrics also mounted at the root for orchestrators that probe /health.
    from app.api.v1.ops import metrics as metrics_endpoint
    from app.api.v1.ops import ready as ready_endpoint

    app.add_api_route("/health", _health, methods=["GET"], include_in_schema=False)
    app.add_api_route("/ready", ready_endpoint, methods=["GET"], include_in_schema=False)
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(404, _not_found_handler)
    app.add_exception_handler(405, _method_not_allowed_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    return app


def _health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "sentinelai", "version": "0.1.0",
                         "env": settings.app_env})


def _not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """Route-level 404s use the same envelope as every other error."""
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found",
                           "message": "The requested endpoint does not exist.",
                           "details": {"path": request.url.path},
                           "request_id": getattr(request.state, "request_id", "unknown")}},
    )


def _method_not_allowed_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=405,
        content={"error": {"code": "method_not_allowed",
                           "message": "That HTTP method is not supported for this endpoint.",
                           "details": {"path": request.url.path},
                           "request_id": getattr(request.state, "request_id", "unknown")}},
    )


def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only field names + short messages; never echo full input back.
    details = [
        {"field": ".".join(str(loc) for loc in err.get("loc", [])),
         "message": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()[:20]
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error",
                           "message": "Request validation failed.",
                           "details": {"errors": details},
                           "request_id": getattr(request.state, "request_id", "unknown")}},
    )


app = create_app()
