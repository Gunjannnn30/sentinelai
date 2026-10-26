"""Policy CRUD + dry-run preview."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.gateway import Policy, PolicyVersion
from app.schemas.common import (
    PolicyDecision,
    PolicyIn,
    PolicyOut,
    PolicyPreviewIn,
    PolicyPreviewOut,
)
from app.services.audit import append_event
from app.services.deps import AuthContext, get_auth, require_role

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=list[PolicyOut])
def list_policies(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[PolicyOut]:
    rows = db.execute(
        select(Policy).where(Policy.org_id == ctx.org_id).order_by(Policy.created_at.desc())
    ).scalars().all()
    return [PolicyOut.model_validate(p) for p in rows]


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    payload: PolicyIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> PolicyOut:
    if payload.scope == "role" and not payload.scope_role:
        from app.core.errors import ValidationError

        raise ValidationError("scope_role is required when scope is 'role'.")
    policy = Policy(
        org_id=ctx.org_id, name=payload.name, description=payload.description,
        enabled=payload.enabled, severity=payload.severity, action=payload.action,
        scope=payload.scope, scope_role=payload.scope_role,
        project_id=payload.project_id if payload.scope == "project" else None,
        conditions=[c.model_dump() for c in payload.conditions], version=1,
    )
    db.add(policy)
    db.flush()
    db.add(PolicyVersion(policy_id=policy.id, version=1,
                         snapshot=_snapshot(policy), changed_by=ctx.user_id))
    append_event(db, org_id=ctx.org_id, event_type="policy.create",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="policy", resource_id=policy.id,
                 detail={"name": policy.name, "action": policy.action})
    db.commit()
    return PolicyOut.model_validate(policy)


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, ctx: AuthContext = Depends(get_auth),
               db: Session = Depends(get_db)) -> PolicyOut:
    policy = _owned(db, policy_id, ctx)
    return PolicyOut.model_validate(policy)


@router.put("/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: str,
    payload: PolicyIn,
    ctx: AuthContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> PolicyOut:
    policy = _owned(db, policy_id, ctx)
    if payload.scope == "role" and not payload.scope_role:
        from app.core.errors import ValidationError

        raise ValidationError("scope_role is required when scope is 'role'.")
    policy.name = payload.name
    policy.description = payload.description
    policy.enabled = payload.enabled
    policy.severity = payload.severity
    policy.action = payload.action
    policy.scope = payload.scope
    policy.scope_role = payload.scope_role
    policy.project_id = payload.project_id if payload.scope == "project" else None
    policy.conditions = [c.model_dump() for c in payload.conditions]
    policy.version += 1
    db.add(PolicyVersion(policy_id=policy.id, version=policy.version,
                         snapshot=_snapshot(policy), changed_by=ctx.user_id))
    append_event(db, org_id=ctx.org_id, event_type="policy.update",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="policy", resource_id=policy.id,
                 detail={"name": policy.name, "version": policy.version,
                         "action": policy.action, "enabled": policy.enabled})
    db.commit()
    return PolicyOut.model_validate(policy)


@router.delete("/{policy_id}", status_code=204, response_class=Response)
def delete_policy(policy_id: str, ctx: AuthContext = Depends(require_role("admin")),
                  db: Session = Depends(get_db)):
    policy = _owned(db, policy_id, ctx)
    append_event(db, org_id=ctx.org_id, event_type="policy.delete",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="policy", resource_id=policy.id,
                 detail={"name": policy.name})
    db.delete(policy)
    db.commit()


@router.post("/preview", response_model=PolicyPreviewOut)
def preview_policy(
    payload: PolicyPreviewIn,
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> PolicyPreviewOut:
    """Dry-run: evaluate an *unsaved* policy draft against sample input.

    Nothing is persisted; the provider is never called.
    """
    from ai.guardrails.injection import detect_injection
    from ai.guardrails.pii import mask_pii
    from ai.guardrails.policy_engine import (
        EvaluationContext,
        PolicyRule,
        evaluate_policies,
    )

    inj = detect_injection(payload.prompt)
    pii = mask_pii(payload.prompt)
    ctx_obj = EvaluationContext(
        prompt=payload.prompt, model=payload.model, provider=payload.provider,
        project_id=payload.project_id, actor_role=payload.actor_role,
        injection_categories=sorted({f.category for f in inj.findings}),
        injection_score=inj.score, injection_severity=inj.max_severity,
        pii_types=pii.types,
    )
    draft = payload.policy
    rule = PolicyRule(
        id="draft", name=draft.name, enabled=draft.enabled, severity=draft.severity,
        action=draft.action, scope=draft.scope, scope_role=draft.scope_role,
        project_id=draft.project_id, conditions=[c.model_dump() for c in draft.conditions],
    )
    decisions = evaluate_policies([rule], ctx_obj)
    decision = decisions[0] if decisions else PolicyDecision(
        policy_id=None, policy_name=draft.name, action="allow",
        severity=draft.severity, matched=False, explanation="Policy not applicable."
    )
    return PolicyPreviewOut(
        decision=decision, injection=inj.as_dict(), pii=pii.as_dict(),
    )


def _snapshot(p: Policy) -> dict:
    return {
        "name": p.name, "description": p.description, "enabled": p.enabled,
        "severity": p.severity, "action": p.action, "scope": p.scope,
        "scope_role": p.scope_role, "project_id": p.project_id,
        "conditions": p.conditions, "version": p.version,
    }


def _owned(db: Session, policy_id: str, ctx: AuthContext) -> Policy:
    policy = db.get(Policy, policy_id)
    if policy is None or policy.org_id != ctx.org_id:
        raise NotFoundError("Policy not found.")
    return policy
