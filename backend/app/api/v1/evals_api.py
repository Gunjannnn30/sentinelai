"""Evaluation datasets, runs, and deterministic metrics.

Runs execute real (or mock) provider calls through the full gateway pipeline,
so a run measures the *actual* system — guardrails, routing and provider —
not an idealized side-channel. Scoring is deterministic only; no LLM judge is
enabled (see ``ai/evaluation/metrics.py``).
"""
from __future__ import annotations

from datetime import UTC, datetime

from ai.evaluation.metrics import evaluate_case, regression_delta, summarize_results
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.session import get_db
from app.models.gateway import EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun
from app.schemas.common import (
    EvalCaseOut,
    EvalDatasetIn,
    EvalDatasetOut,
    EvalRunDetailOut,
    EvalRunIn,
    EvalRunOut,
)
from app.services.audit import append_event
from app.services.deps import AuthContext, require_role
from app.services.request_service import execute_chat

router = APIRouter(prefix="/evals", tags=["evals"])


# ── Datasets ────────────────────────────────────────────────────────────────
@router.get("/datasets", response_model=list[EvalDatasetOut])
def list_datasets(
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[EvalDatasetOut]:
    rows = (
        db.execute(
            select(EvaluationDataset)
            .where(EvaluationDataset.org_id == ctx.org_id)
            .order_by(EvaluationDataset.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[EvalDatasetOut] = []
    for ds in rows:
        count = db.execute(
            select(func.count()).select_from(EvaluationCase).where(EvaluationCase.dataset_id == ds.id)
        ).scalar_one()
        out.append(EvalDatasetOut(**EvalDatasetOut.model_validate(ds).model_dump(), case_count=count))
    return out


@router.post("/datasets", response_model=EvalDatasetOut, status_code=201)
def create_dataset(
    payload: EvalDatasetIn,
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> EvalDatasetOut:
    ds = EvaluationDataset(
        org_id=ctx.org_id, name=payload.name, description=payload.description,
        is_synthetic=True,  # authored in-app → never presented as real telemetry
    )
    db.add(ds)
    db.flush()
    for case in payload.cases:
        db.add(EvaluationCase(
            dataset_id=ds.id, prompt=case.prompt, expected=case.expected,
            reference=case.reference, tags=case.tags,
        ))
    append_event(db, org_id=ctx.org_id, event_type="eval.dataset_created",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="evaluation_dataset", resource_id=ds.id,
                 detail={"name": ds.name, "cases": len(payload.cases)})
    db.commit()
    db.refresh(ds)
    return EvalDatasetOut(**EvalDatasetOut.model_validate(ds).model_dump(),
                          case_count=len(payload.cases))


@router.get("/datasets/{dataset_id}", response_model=EvalDatasetOut)
def get_dataset(
    dataset_id: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> EvalDatasetOut:
    ds = db.get(EvaluationDataset, dataset_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise NotFoundError("Evaluation dataset not found.")
    count = db.execute(
        select(func.count()).select_from(EvaluationCase).where(EvaluationCase.dataset_id == ds.id)
    ).scalar_one()
    return EvalDatasetOut(**EvalDatasetOut.model_validate(ds).model_dump(), case_count=count)


@router.get("/datasets/{dataset_id}/cases", response_model=list[EvalCaseOut])
def list_cases(
    dataset_id: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[EvalCaseOut]:
    ds = db.get(EvaluationDataset, dataset_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise NotFoundError("Evaluation dataset not found.")
    rows = (
        db.execute(select(EvaluationCase).where(EvaluationCase.dataset_id == dataset_id)
                   .order_by(EvaluationCase.created_at.asc()))
        .scalars().all()
    )
    return [EvalCaseOut.model_validate(c) for c in rows]


# ── Runs ────────────────────────────────────────────────────────────────────
@router.post("/runs", response_model=EvalRunOut, status_code=201)
def start_run(
    payload: EvalRunIn,
    ctx: AuthContext = Depends(require_role("developer")),
    db: Session = Depends(get_db),
) -> EvalRunOut:
    ds = db.get(EvaluationDataset, payload.dataset_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise NotFoundError("Evaluation dataset not found.")
    cases = (
        db.execute(select(EvaluationCase).where(EvaluationCase.dataset_id == ds.id))
        .scalars().all()
    )
    if not cases:
        raise ValidationError("Dataset has no cases to evaluate.")

    run = EvaluationRun(
        org_id=ctx.org_id, dataset_id=ds.id, name=payload.name,
        model_keys=payload.model_keys, status="running",
        baseline_run_id=payload.baseline_run_id,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()

    results: list[dict] = []
    for case in cases:
        for model_key in payload.model_keys:
            outcome, record = execute_chat(
                db, org_id=ctx.org_id, project_id=None,
                actor_user_id=ctx.user_id, actor_email=ctx.email,
                actor_role=ctx.role,
                messages=[{"role": "user", "content": case.prompt}],
                requested_model=model_key, max_tokens=None, temperature=0.0,
                dry_run=False,
            )
            ok = outcome.status == "success"
            had_violation = outcome.policy_outcome == "block" or any(
                f.get("action_taken") == "block" for f in outcome.findings
            )
            metrics = evaluate_case(outcome.content or "", case.expected, case.reference,
                                    had_violation=had_violation, ok=ok)
            row = EvaluationResult(
                run_id=run.id, case_id=case.id, model_key=model_key,
                status=outcome.status, output=outcome.content,
                error_category=(outcome.error or {}).get("category") if outcome.error else None,
                latency_ms=outcome.latency_ms,
                total_tokens=outcome.usage.get("total_tokens"),
                estimated_cost_usd=outcome.estimated_cost_usd,
                metrics=metrics,
            )
            db.add(row)
            results.append({
                "model_key": model_key, "status": row.status, "metrics": metrics,
                "latency_ms": row.latency_ms, "estimated_cost_usd": row.estimated_cost_usd,
            })

    run.summary = summarize_results(results)
    baseline = None
    if payload.baseline_run_id:
        base_run = db.get(EvaluationRun, payload.baseline_run_id)
        if base_run is not None and base_run.org_id == ctx.org_id:
            baseline = base_run.summary
    run.summary["regression"] = regression_delta(baseline, run.summary)
    run.status = "completed"
    run.finished_at = datetime.now(UTC)

    append_event(db, org_id=ctx.org_id, event_type="eval.run_completed",
                 actor_user_id=ctx.user_id, actor_email=ctx.email,
                 resource_type="evaluation_run", resource_id=run.id,
                 detail={"name": run.name, "models": payload.model_keys,
                         "cases": len(cases)})
    db.commit()
    db.refresh(run)
    return EvalRunOut.model_validate(run)


@router.get("/runs", response_model=list[EvalRunOut])
def list_runs(
    dataset_id: str | None = None,
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[EvalRunOut]:
    stmt = select(EvaluationRun).where(EvaluationRun.org_id == ctx.org_id)
    if dataset_id:
        stmt = stmt.where(EvaluationRun.dataset_id == dataset_id)
    rows = (db.execute(stmt.order_by(EvaluationRun.created_at.desc())).scalars().all())
    return [EvalRunOut.model_validate(r) for r in rows]


@router.get("/runs/{run_id}", response_model=EvalRunDetailOut)
def get_run(
    run_id: str,
    ctx: AuthContext = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> EvalRunDetailOut:
    run = db.get(EvaluationRun, run_id)
    if run is None or run.org_id != ctx.org_id:
        raise NotFoundError("Evaluation run not found.")
    from app.schemas.common import EvalResultOut

    results = (
        db.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
        .scalars().all()
    )
    detail = EvalRunDetailOut.model_validate(run)
    detail.results = [EvalResultOut.model_validate(r) for r in results]
    return detail
