"""First-boot seeding: a demo organization with a working local (mock) provider.

Everything created here is clearly marked ``is_demo_data`` or named "Local
(simulated)" so demo metrics are never mistaken for real telemetry.
"""
from __future__ import annotations

import re
import secrets
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.gateway import ModelConfig, Policy, Provider
from app.models.identity import Membership, Organization, Project, Team, User
from app.services.request_service import DEFAULT_POLICY_DEFS

log = get_logger("seed")

DEMO_USER_EMAIL = "demo@sentinelai.dev"
DEMO_PASSWORD = "demo-password-123"  # development-only seeded account, printed in README


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "org"


def _unique_slug(db: Session, base: str) -> str:
    """Org slugs are globally unique; dedupe with a short suffix instead of a 500."""
    slug = base
    for i in range(2, 50):
        taken = db.execute(select(Organization.id).where(Organization.slug == slug)).scalar_one_or_none()
        if taken is None:
            return slug
        slug = f"{base}-{i}"
    return f"{base}-{secrets.token_hex(3)}"


def provision_org(
    db: Session,
    *,
    org_name: str,
    owner_email: str,
    password_hash: str,
    full_name: str = "",
    with_local_provider: bool = True,
) -> tuple[Organization, User]:
    """Create an org + owner + default project/team/policies/(mock) provider."""
    org = Organization(name=org_name, slug=_unique_slug(db, slugify(org_name)))
    db.add(org)
    db.flush()

    user = User(email=owner_email.lower(), full_name=full_name or owner_email,
                password_hash=password_hash)
    db.add(user)
    db.flush()

    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    db.add(Project(org_id=org.id, name="Default", slug="default",
                   description="Default project", is_default=True))
    db.add(Team(org_id=org.id, name="Platform"))
    db.flush()

    for d in DEFAULT_POLICY_DEFS:
        db.add(Policy(org_id=org.id, name=d["name"], description=d["description"],
                      severity=d["severity"], action=d["action"], enabled=True,
                      scope="organization", conditions=d["conditions"], version=1))

    if with_local_provider:
        provider = Provider(org_id=org.id, kind="mock", name="Local (simulated)",
                            base_url="", secret_ref="", enabled=True)
        db.add(provider)
        db.flush()
        for key, label, ctx in (
            ("sentinel-mock-small", "Sentinel Mock Small (simulated)", 8192),
            ("sentinel-mock-large", "Sentinel Mock Large (simulated)", 32768),
        ):
            db.add(ModelConfig(
                org_id=org.id, provider_id=provider.id, model_key=key,
                display_name=label, capabilities=["chat"], context_window=ctx,
                input_cost_per_1m=0.0, output_cost_per_1m=0.0,
                pricing_source="simulated zero-cost (mock provider)",
                priority=50 if "small" in key else 60, latency_class="fast",
                enabled=True, is_demo_data=True,
            ))
    return org, user


def seed_demo_if_empty(db: Session) -> bool:
    """Called at startup. Idempotent: only seeds when the DB has no users."""
    if not settings.seed_demo_data:
        return False
    existing = db.execute(select(User.id).limit(1)).scalar_one_or_none()
    if existing:
        return False
    org, user = provision_org(
        db,
        org_name="Acme Corp (Demo)",
        owner_email=DEMO_USER_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name="Demo Owner",
    )
    db.commit()
    log.info("Seeded demo organization and local provider.",
             extra={"org_id": org.id, "user": DEMO_USER_EMAIL})
    return True
