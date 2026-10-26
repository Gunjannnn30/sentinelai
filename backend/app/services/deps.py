"""FastAPI dependencies: session identity, role gates, tenant scoping."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import get_identity, role_at_least
from app.db.session import get_db


@dataclass
class AuthContext:
    """Resolved once per request; every query filters through ``org_id``."""

    user_id: str
    org_id: str
    role: str
    email: str

    def require(self, minimum: str) -> None:
        if not role_at_least(self.role, minimum):
            raise ForbiddenError(
                f"Role '{self.role}' is not permitted to perform this action "
                f"(requires '{minimum}' or higher)."
            )


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    ident = get_identity(request)
    # Re-validate against the DB each request (revocation, deactivated users,
    # org membership changes take effect immediately).
    from app.models.identity import Membership, User

    user = db.get(User, ident.user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("Account is inactive or no longer exists.")
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == ident.user_id, Membership.org_id == ident.org_id)
        .first()
    )
    if not membership:
        raise ForbiddenError("You are not a member of this organization.")
    return AuthContext(user_id=user.id, org_id=membership.org_id, role=membership.role,
                       email=user.email)


def require_role(minimum: str):
    def _dep(ctx: AuthContext = Depends(get_auth)) -> AuthContext:
        ctx.require(minimum)
        return ctx

    return _dep


def get_owned_org_model(model_cls, object_id: str, ctx: AuthContext, db: Session,
                        not_found: str = "Resource not found."):
    """Fetch a tenant-owned row or 404 — never leaks cross-org existence."""
    obj = db.get(model_cls, object_id)
    if obj is None or getattr(obj, "org_id", None) != ctx.org_id:
        raise NotFoundError(not_found)
    return obj
