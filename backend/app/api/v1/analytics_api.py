"""Analytics: overview, cost, security, model performance — all from persisted rows."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.gateway import RequestRecord, SecurityEvent
from app.models.identity import Organization
from app.schemas.common import (
    AnalyticsOut,
    CostBreakdownRow,
    ModelAnalyticsOut,
    ModelAnalyticsRow,
    OverviewOut,
    SecurityAnalyticsOut,
)
from app.services.deps import AuthContext, get_auth

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _day_start(days: int) -> datetime:
    d = date.today() - timedelta(days=days - 1)
    return datetime.combine(d, time.min, tzinfo=UTC)


def _series_dates(days: int) -> list[date]:
    return [date.today() - timedelta(days=days - 1 - i) for i in range(days)]


@router.get("/overview", response_model=OverviewOut)
def overview(
    days: int = Query(default=7, ge=1, le=90),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> OverviewOut:
    since = _day_start(days)
    base = select(func.count()).select_from(RequestRecord).where(
        RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since
    )
    total = db.execute(base).scalar_one()
    by_status = dict(
        db.execute(
            select(RequestRecord.status, func.count())
            .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since)
            .group_by(RequestRecord.status)
        ).all()
    )
    ok = by_status.get("success", 0)
    blocked = by_status.get("blocked", 0)
    errors = by_status.get("error", 0)

    avg_lat = db.execute(
        select(func.avg(RequestRecord.latency_ms)).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
            RequestRecord.latency_ms.is_not(None),
        )
    ).scalar_one()

    cost_row = db.execute(
        select(
            func.sum(RequestRecord.estimated_cost_usd),
            func.count(RequestRecord.estimated_cost_usd),
        ).where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
                RequestRecord.status == "success")
    ).one()
    spend, priced_count = cost_row
    # spend is None-ish when no priced rows exist → report unavailable, not 0.
    pricing_available = bool(priced_count) and spend is not None

    decided = ok + blocked + errors
    pass_rate = (ok / decided) if decided else None

    uniq_models = db.execute(
        select(func.count(func.distinct(RequestRecord.model_key))).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
            RequestRecord.model_key.is_not(None),
        )
    ).scalar_one()

    # Volume series per day
    rows = db.execute(
        select(func.date(RequestRecord.created_at), RequestRecord.status, func.count())
        .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since)
        .group_by(func.date(RequestRecord.created_at), RequestRecord.status)
    ).all()
    buckets: dict[str, dict] = {d.isoformat(): {"date": d.isoformat(), "total": 0,
                                                "success": 0, "blocked": 0, "error": 0}
                                for d in _series_dates(days)}
    for day, status, count in rows:
        key = str(day)
        if key in buckets:
            buckets[key]["total"] += count
            buckets[key][status] = count  # group by status → distinct keys
    # recompute totals safely
    for v in buckets.values():
        v["total"] = v["success"] + v["blocked"] + v["error"]

    demo = db.execute(
        select(func.count()).select_from(RequestRecord).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.is_demo_data.is_(True),
            RequestRecord.created_at >= since,
        )
    ).scalar_one()

    return OverviewOut(
        total_requests=total,
        successful_requests=ok,
        blocked_requests=blocked,
        error_requests=errors,
        avg_latency_ms=round(float(avg_lat), 1) if avg_lat is not None else None,
        estimated_spend_usd=round(float(spend), 6) if pricing_available else None,
        spend_pricing_available=pricing_available,
        policy_pass_rate=round(pass_rate, 4) if pass_rate is not None else None,
        unique_models=uniq_models,
        demo_data_included=demo > 0,
        series=[buckets[k] for k in sorted(buckets)],
    )


@router.get("/costs", response_model=AnalyticsOut)
def costs(
    days: int = Query(default=30, ge=1, le=90),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> AnalyticsOut:
    since = _day_start(days)
    org = db.get(Organization, ctx.org_id)

    def agg(group_col):
        return db.execute(
            select(group_col, func.count(), func.coalesce(func.sum(RequestRecord.total_tokens), 0),
                   func.sum(RequestRecord.estimated_cost_usd),
                   func.count(RequestRecord.estimated_cost_usd))
            .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
                   RequestRecord.status == "success")
            .group_by(group_col)
        ).all()

    def to_rows(rows, key_fn) -> list[CostBreakdownRow]:
        out = []
        for r in rows:
            key = key_fn(r)
            count = int(r[1])
            tokens = int(r[2])
            spend, priced = r[3], int(r[4])
            available = priced > 0 and spend is not None
            out.append(CostBreakdownRow(
                key=key, requests=count, tokens=tokens,
                cost_usd=round(float(spend), 6) if available else None,
                pricing_available=bool(available),
            ))
        return sorted(out, key=lambda x: -(x.cost_usd or 0))

    by_provider = to_rows(agg(RequestRecord.provider_kind),
                          lambda r: r[0] or "unknown")
    by_model = to_rows(agg(RequestRecord.model_key), lambda r: r[0] or "unknown")

    daily_rows = db.execute(
        select(func.date(RequestRecord.created_at),
               func.count(RequestRecord.estimated_cost_usd),
               func.sum(RequestRecord.estimated_cost_usd),
               func.coalesce(func.sum(RequestRecord.total_tokens), 0),
               func.count())
        .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
               RequestRecord.status == "success")
        .group_by(func.date(RequestRecord.created_at))
    ).all()
    daily_map = {str(d): (int(priced), float(spend or 0), int(tokens), int(total))
                 for d, priced, spend, tokens, total in daily_rows}
    daily = []
    for d in _series_dates(days):
        priced, spend, tokens, total = daily_map.get(d.isoformat(), (0, 0.0, 0, 0))
        daily.append({
            "date": d.isoformat(),
            "cost_usd": round(spend, 6) if priced > 0 else None,
            "pricing_available": priced > 0,
            "tokens": tokens,
            "requests": total,
        })

    month_start = datetime.combine(date.today().replace(day=1), time.min, tzinfo=UTC)
    mtd = db.execute(
        select(func.sum(RequestRecord.estimated_cost_usd), func.count(RequestRecord.estimated_cost_usd))
        .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= month_start,
               RequestRecord.status == "success")
    ).one()
    mtd_spend, mtd_priced = mtd
    mtd_val = round(float(mtd_spend), 6) if (mtd_priced and mtd_spend is not None) else None

    return AnalyticsOut(
        by_provider=by_provider, by_model=by_model, daily=daily,
        budget_monthly_usd=org.budget_monthly_usd if org else None,
        month_to_date_usd=mtd_val,
        pricing_source_note=(
            "Estimated costs use per-model list prices stored on each model configuration "
            "(`pricing_source` field). Models without stored pricing are shown as unavailable, "
            "never as $0. Mock/simulated models have zero cost by definition."
        ),
    )


@router.get("/security", response_model=SecurityAnalyticsOut)
def security(
    days: int = Query(default=30, ge=1, le=90),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> SecurityAnalyticsOut:
    since = _day_start(days)
    blocked = db.execute(
        select(func.count()).select_from(RequestRecord).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
            RequestRecord.status == "blocked")
    ).scalar_one()

    def category_count(prefix: str) -> int:
        return db.execute(
            select(func.count()).select_from(SecurityEvent).where(
                SecurityEvent.org_id == ctx.org_id, SecurityEvent.created_at >= since,
                SecurityEvent.category.like(f"{prefix}%"))
        ).scalar_one()

    injections = category_count("prompt_injection")
    pii = category_count("pii_detected")
    violations = category_count("policy_violation")

    by_severity = dict(db.execute(
        select(SecurityEvent.severity, func.count())
        .where(SecurityEvent.org_id == ctx.org_id, SecurityEvent.created_at >= since)
        .group_by(SecurityEvent.severity)
    ).all())

    top_rules = [
        {"rule": rule, "count": count, "severity": sev}
        for rule, count, sev in db.execute(
            select(SecurityEvent.rule_name, func.count(), func.max(SecurityEvent.severity))
            .where(SecurityEvent.org_id == ctx.org_id, SecurityEvent.created_at >= since)
            .group_by(SecurityEvent.rule_name)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
    ]

    rows = db.execute(
        select(func.date(SecurityEvent.created_at), SecurityEvent.category, func.count())
        .where(SecurityEvent.org_id == ctx.org_id, SecurityEvent.created_at >= since)
        .group_by(func.date(SecurityEvent.created_at), SecurityEvent.category)
    ).all()
    series: dict[str, dict] = {d.isoformat(): {"date": d.isoformat(), "prompt_injection": 0,
                                               "pii_detected": 0, "policy_violation": 0}
                               for d in _series_dates(days)}
    for day, cat, count in rows:
        key = str(day)
        base_cat = cat.split(":")[0]
        if key in series and base_cat in series[key]:
            series[key][base_cat] += count

    return SecurityAnalyticsOut(
        blocked_requests=blocked, injection_detections=injections,
        pii_masking_events=pii, policy_violations=violations,
        by_severity=by_severity, top_rules=top_rules,
        series=[series[k] for k in sorted(series)],
    )


@router.get("/models", response_model=ModelAnalyticsOut)
def model_analytics(
    days: int = Query(default=30, ge=1, le=90),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ModelAnalyticsOut:
    since = _day_start(days)
    rows = db.execute(
        select(RequestRecord.model_key, RequestRecord.provider_kind,
               func.count(),
               func.sum(func.case((RequestRecord.status == "error", 1), else_=0)),
               func.avg(RequestRecord.latency_ms),
               func.coalesce(func.sum(RequestRecord.total_tokens), 0),
               func.sum(RequestRecord.estimated_cost_usd),
               func.count(RequestRecord.estimated_cost_usd))
        .where(RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
               RequestRecord.model_key.is_not(None))
        .group_by(RequestRecord.model_key, RequestRecord.provider_kind)
    ).all()

    # p95 needs the raw latencies — fetch per model in one pass.
    lat_rows = db.execute(
        select(RequestRecord.model_key, RequestRecord.latency_ms).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.created_at >= since,
            RequestRecord.latency_ms.is_not(None), RequestRecord.model_key.is_not(None))
    ).all()
    latencies: dict[str, list[int]] = {}
    for mk, ms in lat_rows:
        latencies.setdefault(mk, []).append(int(ms))

    out_rows = []
    for model_key, provider_kind, cnt, err_cnt, avg_lat, tokens, spend, priced in rows:
        cnt = int(cnt)
        err_cnt = int(err_cnt)
        lats = sorted(latencies.get(model_key, []))
        p95 = lats[int(len(lats) * 0.95) - 1] if len(lats) >= 5 else None
        available = int(priced) > 0 and spend is not None
        out_rows.append(ModelAnalyticsRow(
            model_key=model_key, provider_kind=provider_kind or "unknown",
            requests=cnt, errors=err_cnt,
            error_rate=round(err_cnt / cnt, 4) if cnt else 0.0,
            avg_latency_ms=round(float(avg_lat), 1) if avg_lat is not None else None,
            p95_latency_ms=p95, total_tokens=int(tokens),
            est_cost_usd=round(float(spend), 6) if available else None,
            pricing_available=bool(available),
        ))
    out_rows.sort(key=lambda r: -r.requests)
    demo = db.execute(
        select(func.count()).select_from(RequestRecord).where(
            RequestRecord.org_id == ctx.org_id, RequestRecord.is_demo_data.is_(True),
            RequestRecord.created_at >= since)
    ).scalar_one()
    return ModelAnalyticsOut(rows=out_rows, demo_data_included=demo > 0)
