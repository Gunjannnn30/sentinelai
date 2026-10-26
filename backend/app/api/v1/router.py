"""Versioned API router. Every feature router is registered here."""

from fastapi import APIRouter

from app.api.v1 import (
    admin_api,
    analytics_api,
    auth,
    evals_api,
    gateway,
    ops,
    policies_api,
    requests_api,
)

api_router = APIRouter()
api_router.include_router(ops.router)
api_router.include_router(auth.router)
api_router.include_router(gateway.router)
api_router.include_router(requests_api.router)
api_router.include_router(policies_api.router)
api_router.include_router(analytics_api.router)
api_router.include_router(evals_api.router)
api_router.include_router(admin_api.router)
