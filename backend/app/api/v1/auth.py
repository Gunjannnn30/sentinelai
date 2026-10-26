"""Authentication routes: register, login, dev-login (dev only), logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    create_session_token,
    get_identity,
    hash_password,
    new_csrf_token,
    verify_password,
)
from app.db.session import get_db
from app.models.identity import Membership, Organization, User
from app.schemas.common import DevLoginIn, LoginIn, MeOut, OrgOut, RegisterIn, UserOut
from app.services.audit import append_event
from app.services.deps import AuthContext, get_auth
from app.services.ratelimit import check_rate_limit
from app.services.seed import DEMO_USER_EMAIL, provision_org

log = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort client address for credential-stuffing throttling.

    Honours ``X-Forwarded-For`` when present (proxy deployments); otherwise the
    socket peer address. Test clients report ``testclient``.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _throttle_login(request: Request, email: str) -> None:
    """Per-(IP, email) sliding-window guard on authentication attempts.

    Scoped to the pair rather than the IP alone so one noisy client cannot lock
    out an entire office, and to the email rather than the IP alone so a
    distributed spray against one account is still throttled.
    """
    check_rate_limit(
        f"login:{_client_ip(request)}:{email}",
        settings.login_rate_limit_per_minute,
    )


def _establish_session(response: Response, user: User, org_id: str, role: str) -> str:
    csrf = new_csrf_token()
    token = create_session_token(
        {"user_id": user.id, "org_id": org_id, "role": role, "email": user.email, "csrf": csrf}
    )
    response.set_cookie(
        settings.session_cookie_name, token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True, samesite="lax", secure=settings.session_cookie_secure,
        path="/",
    )
    # Readable by JS on purpose: it is mirrored into the X-CSRF-Token header.
    response.set_cookie(
        settings.csrf_cookie_name, csrf,
        max_age=settings.session_ttl_hours * 3600,
        httponly=False, samesite="lax", secure=settings.session_cookie_secure,
        path="/",
    )
    return csrf


@router.post("/register", response_model=MeOut, status_code=201)
def register(request: Request, payload: RegisterIn, response: Response,
             db: Session = Depends(get_db)) -> MeOut:
    email = payload.email.lower()
    # Sign-up abuse guard (per-IP): a burst of registrations from one address
    # is the cheap way to farm orgs and pollute the audit trail.
    check_rate_limit(f"register:{_client_ip(request)}", settings.login_rate_limit_per_minute)
    if db.execute(select(User.id).where(User.email == email)).scalar_one_or_none():
        raise ConflictError("An account with that email already exists.")
    org, user = provision_org(
        db, org_name=payload.org_name, owner_email=email,
        password_hash=hash_password(payload.password), full_name=payload.full_name,
    )
    append_event(db, org_id=org.id, event_type="auth.register", actor_user_id=user.id,
                 actor_email=email, resource_type="user", resource_id=user.id,
                 detail={"org": org.name})
    db.commit()
    csrf = _establish_session(response, user, org.id, "owner")
    log.info("User registered.", extra={"user_id": user.id, "org_id": org.id})
    return MeOut(user=UserOut.model_validate(user), org=OrgOut.model_validate(org),
                 role="owner", csrf_token=csrf,
                 available_providers=settings.provider_keys())


@router.post("/login", response_model=MeOut)
def login(request: Request, payload: LoginIn, response: Response,
          db: Session = Depends(get_db)) -> MeOut:
    email = payload.email.lower()
    _throttle_login(request, email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password.")
    if not user.is_active:
        raise UnauthorizedError("Account is deactivated.")
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id)
    ).scalars().first()
    if not membership:
        raise UnauthorizedError("No organization membership found for this account.")
    org = db.get(Organization, membership.org_id)
    assert org is not None
    csrf = _establish_session(response, user, org.id, membership.role)
    append_event(db, org_id=org.id, event_type="auth.login", actor_user_id=user.id,
                 actor_email=email, resource_type="session", detail={"role": membership.role})
    db.commit()
    return MeOut(user=UserOut.model_validate(user), org=OrgOut.model_validate(org),
                 role=membership.role, csrf_token=csrf,
                 available_providers=settings.provider_keys())


@router.post("/dev-login", response_model=MeOut)
def dev_login(request: Request, payload: DevLoginIn, response: Response,
              db: Session = Depends(get_db)) -> MeOut:
    """Development-only sign-in without a password.

    Guard rails: disabled in production, disabled when ALLOW_DEV_LOGIN=false,
    and never creates a session for a non-existent account.
    """
    if settings.is_production or not settings.allow_dev_login:
        raise UnauthorizedError("Development login is disabled.", code="dev_login_disabled")
    email = payload.email.lower()
    _throttle_login(request, email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise UnauthorizedError(f"No development account '{email}'. "
                                f"Try '{DEMO_USER_EMAIL}' or register first.")
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id)
    ).scalars().first()
    if not membership:
        raise UnauthorizedError("No organization membership found for this account.")
    org = db.get(Organization, membership.org_id)
    assert org is not None
    csrf = _establish_session(response, user, org.id, membership.role)
    append_event(db, org_id=org.id, event_type="auth.dev_login", actor_user_id=user.id,
                 actor_email=email, resource_type="session",
                 detail={"role": membership.role})
    db.commit()
    return MeOut(user=UserOut.model_validate(user), org=OrgOut.model_validate(org),
                 role=membership.role, csrf_token=csrf,
                 available_providers=settings.provider_keys())


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(request: Request, ctx: AuthContext = Depends(get_auth),
       db: Session = Depends(get_db)) -> MeOut:
    user = db.get(User, ctx.user_id)
    org = db.get(Organization, ctx.org_id)
    assert user is not None and org is not None
    csrf = request.cookies.get(settings.csrf_cookie_name, "")
    return MeOut(user=UserOut.model_validate(user), org=OrgOut.model_validate(org),
                 role=ctx.role, csrf_token=csrf,
                 available_providers=settings.provider_keys())


@router.post("/switch-org", response_model=MeOut)
def switch_org(payload: dict, request: Request, response: Response,
               ctx: AuthContext = Depends(get_auth),
               db: Session = Depends(get_db)) -> MeOut:
    """Switch active organization membership (multi-org users)."""
    org_id = str(payload.get("org_id", ""))
    membership = db.execute(
        select(Membership).where(Membership.user_id == ctx.user_id, Membership.org_id == org_id)
    ).scalar_one_or_none()
    if membership is None:
        raise ValidationError("You are not a member of that organization.")
    user = db.get(User, ctx.user_id)
    org = db.get(Organization, org_id)
    assert user is not None and org is not None
    csrf = _establish_session(response, user, org.id, membership.role)
    return MeOut(user=UserOut.model_validate(user), org=OrgOut.model_validate(org),
                 role=membership.role, csrf_token=csrf,
                 available_providers=settings.provider_keys())


def get_session_identity(request: Request) -> str:  # pragma: no cover - helper
    return get_identity(request).user_id
