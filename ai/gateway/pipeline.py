"""The request pipeline — pure orchestration, DB-agnostic.

Order (mirrors docs/ARCHITECTURE.md §Pipeline):

  inbound → schema validation (API layer) → rate/size limits (API layer)
  → injection scan → PII detection/masking → policy evaluation
  → output-policy pre-check → routing → provider call (bounded retries)
  → output inspection → result (persistence handled by the caller)

The pipeline never fabricates a provider success: any provider failure is
returned as a structured error with a category.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai.guardrails.injection import InjectionConfig, detect_injection
from ai.guardrails.output_guard import check_output
from ai.guardrails.pii import PiiConfig, mask_pii
from ai.guardrails.policy_engine import (
    EvaluationContext,
    PolicyRule,
    effective_action,
    evaluate_policies,
)
from ai.providers.base import ChatRequest, ProviderAdapter, ProviderError, ProviderResponse
from ai.routing.engine import Candidate, RoutingConstraints, RoutingResult, route

MAX_RETRIES_DEFAULT = 2
_RETRY_BACKOFF_SECONDS = (0.2, 0.5)  # bounded, short — per attempt after the first


@dataclass
class PipelineConfig:
    timeout_seconds: float = 60.0
    max_retries: int = MAX_RETRIES_DEFAULT
    store_content: bool = False
    injection: InjectionConfig = field(default_factory=InjectionConfig)
    pii: PiiConfig = field(default_factory=PiiConfig)
    mask_pii: bool = True
    prohibited_output_patterns: list[str] = field(default_factory=list)
    # per-request PII mask index is built fresh each call (irreversible)


@dataclass
class PipelineRequest:
    messages: list[dict[str, str]]
    model: str | None = None            # requested/pinned model key
    project_id: str | None = None
    actor_role: str = "developer"
    max_tokens: int | None = None
    temperature: float | None = None
    dry_run: bool = False


@dataclass
class PipelineOutcome:
    status: str                       # success | blocked | error | dry_run
    content: str | None = None
    policy_outcome: str = "allow"     # allow | warn | block
    findings: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    injection: dict = field(default_factory=dict)
    pii: dict = field(default_factory=dict)
    routing: dict = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    usage: dict = field(default_factory=dict)
    estimated_cost_usd: float | None = None
    cost_pricing_source: str | None = None
    error: dict | None = None         # {category, message, retryable}
    blocked_reason: str | None = None
    sanitized_messages: list[dict[str, str]] = field(default_factory=list)
    output_findings: list[dict] = field(default_factory=list)


def estimate_cost(
    model_cfg: Any, prompt_tokens: int | None, completion_tokens: int | None
) -> tuple[float | None, str | None]:
    """Return (cost_usd, pricing_source). (None, None) = pricing unavailable."""
    if model_cfg is None:
        return None, None
    if model_cfg.input_cost_per_1m is None or model_cfg.output_cost_per_1m is None:
        return None, None
    if prompt_tokens is None and completion_tokens is None:
        return None, None
    cost = (
        (prompt_tokens or 0) / 1_000_000.0 * model_cfg.input_cost_per_1m
        + (completion_tokens or 0) / 1_000_000.0 * model_cfg.output_cost_per_1m
    )
    return round(cost, 8), model_cfg.pricing_source


def _findings_from_injection(result) -> list[dict]:
    out = []
    for f in result.findings:
        out.append({
            "category": f"prompt_injection:{f.category}",
            "severity": f.severity,
            "rule_name": f"{f.rule_id} — {f.description}",
            "action_taken": "block",
            "detail": f"Matched: {f.excerpt[:160]}",
            "masked_types": [],
        })
    return out


def run_pipeline(
    req: PipelineRequest,
    *,
    policies: list[PolicyRule],
    candidates: list[Candidate],
    build_adapter: Callable[[str], ProviderAdapter],
    model_lookup: Callable[[str], Any],
    routing_constraints: RoutingConstraints | None = None,
    config: PipelineConfig | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> PipelineOutcome:
    """Execute the guardrail → routing → provider pipeline.

    ``build_adapter(provider_kind)`` returns an adapter for a routed model;
    ``model_lookup(model_key)`` returns the DB ModelConfig (for pricing).
    """
    cfg = config or PipelineConfig()
    prompt_text = "\n".join(m["content"] for m in req.messages if m.get("content"))

    # ── 1. injection scan ────────────────────────────────────────────────
    injection = detect_injection(prompt_text, cfg.injection)

    # ── 2. PII detection + masking (irreversible) ────────────────────────
    masked_messages: list[dict[str, str]] = []
    pii_matches_total: list[str] = []
    for m in req.messages:
        if cfg.mask_pii:
            res = mask_pii(m.get("content", ""), cfg.pii)
            masked_messages.append({"role": m["role"], "content": res.text})
            pii_matches_total.extend(res.types)
        else:
            masked_messages.append({"role": m["role"], "content": m.get("content", "")})
    pii_summary = {
        "found": bool(pii_matches_total),
        "types": sorted(set(pii_matches_total)),
        "count": len(pii_matches_total),
        "masking": "irreversible" if cfg.mask_pii else "off",
    }
    findings: list[dict] = _findings_from_injection(injection)
    if pii_summary["found"]:
        findings.append({
            "category": "pii_detected",
            "severity": "medium",
            "rule_name": "PII detection",
            "action_taken": "mask" if cfg.mask_pii else "warn",
            "detail": f"Detected types: {', '.join(pii_summary['types'])} "
                      f"({'masked irreversibly' if cfg.mask_pii else 'masking disabled'}).",
            "masked_types": pii_summary["types"],
        })

    # ── 3. policy evaluation ─────────────────────────────────────────────
    ctx = EvaluationContext(
        prompt=prompt_text,
        model=req.model,
        project_id=req.project_id,
        actor_role=req.actor_role,
        injection_categories=sorted({f.category for f in injection.findings}),
        injection_score=injection.score,
        injection_severity=injection.max_severity,
        pii_types=pii_summary["types"],
    )
    decisions = evaluate_policies(policies, ctx)
    action, trigger = effective_action(decisions)
    for d in decisions:
        if d.matched and d.action in ("mask", "warn"):
            findings.append({
                "category": "policy_violation",
                "severity": d.severity,
                "rule_name": d.policy_name,
                "action_taken": d.action,
                "detail": d.explanation,
                "masked_types": [],
            })

    # A policy may force exclusion of models
    excluded_models: list[str] = []
    for d in decisions:
        if d.matched and d.action == "block":
            for cond in d.matched_conditions:
                if cond.get("field") == "model" and cond.get("op") in ("equals", "in"):
                    values = cond.get("value") if isinstance(cond.get("value"), list) else [cond.get("value")]
                    excluded_models.extend(str(v) for v in values if v)

    policy_outcome = {"allow": "allow", "warn": "warn", "mask": "warn", "block": "block"}[action]

    common = dict(
        policy_outcome=policy_outcome,
        findings=findings,
        decisions=[d.as_dict() for d in decisions],
        injection=injection.as_dict(),
        pii=pii_summary,
        sanitized_messages=masked_messages,
    )

    if action == "block":
        reason = (
            trigger.explanation
            if trigger
            else "Blocked by security policy."
        )
        return PipelineOutcome(
            status="blocked",
            blocked_reason=reason,
            error={
                "category": "policy_blocked",
                "message": "Request blocked by organization security policy before reaching any model.",
                "retryable": False,
            },
            **common,
        )

    # ── 4. routing (fail-closed) ─────────────────────────────────────────
    cons = routing_constraints or RoutingConstraints()
    if excluded_models:
        cons.exclude_models = sorted(set(cons.exclude_models) | set(excluded_models))
    if req.model:
        cons.preferred_model = req.model
    routing: RoutingResult = route(candidates, cons)
    routing_dict = routing.as_dict()

    if not routing.ok:
        return PipelineOutcome(
            status="blocked",
            blocked_reason=routing.explanation,
            routing=routing_dict,
            error={
                "category": "no_compliant_model",
                "message": routing.explanation,
                "retryable": False,
            },
            **common,
        )

    winner = routing.selected
    assert winner is not None
    provider_kind = winner.provider_kind
    model_key = winner.model_key

    if req.dry_run:
        return PipelineOutcome(
            status="dry_run",
            model=model_key,
            provider=provider_kind,
            routing=routing_dict,
            content=None,
            **common,
        )

    # ── 5. provider call with bounded retries (transient only) ───────────
    chat_req = ChatRequest(
        messages=masked_messages,
        model=model_key,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    adapter = build_adapter(provider_kind)
    attempts = 0
    last_error: ProviderError | None = None
    started = time.perf_counter()
    response: ProviderResponse | None = None

    while attempts <= cfg.max_retries:
        attempts += 1
        try:
            response = adapter.chat(chat_req)
            last_error = None
            break
        except ProviderError as exc:
            last_error = exc
            if not exc.retryable or attempts > cfg.max_retries:
                break
            delay = _RETRY_BACKOFF_SECONDS[min(attempts - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
            sleep(delay)

    if last_error is not None or response is None:
        err = last_error or ProviderError("Provider returned no response.",
                                          category="unavailable", provider=provider_kind)
        return PipelineOutcome(
            status="error",
            provider=provider_kind,
            model=model_key,
            routing=routing_dict,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error={
                "category": err.category,
                "message": err.message,
                "retryable": err.retryable,
                "attempts": attempts,
            },
            **common,
        )

    # ── 6. output inspection ─────────────────────────────────────────────
    out_check = check_output(
        response.content,
        prohibited_patterns=cfg.prohibited_output_patterns,
        pii_config=cfg.pii,
        mask_pii_in_output=cfg.mask_pii,
    )
    out_findings = [f.as_dict() for f in out_check.findings]

    if out_check.action == "block":
        detail = "; ".join(f["detail"] for f in out_findings)
        findings.append({
            "category": "output_policy",
            "severity": "high",
            "rule_name": "Output security policy",
            "action_taken": "block",
            "detail": detail,
            "masked_types": [],
        })
        return PipelineOutcome(
            status="blocked",
            provider=provider_kind,
            model=model_key,
            routing=routing_dict,
            blocked_reason="Response blocked by output security policy.",
            output_findings=out_findings,
            latency_ms=response.latency_ms or int((time.perf_counter() - started) * 1000),
            error={
                "category": "policy_blocked",
                "message": "Model response was blocked by output security policy.",
                "retryable": False,
            },
            **common,
        )

    for f in out_findings:
        findings.append({
            "category": "output_policy",
            "severity": f["severity"],
            "rule_name": "Output security policy",
            "action_taken": out_check.action,
            "detail": f["detail"],
            "masked_types": [],
        })

    model_cfg = model_lookup(model_key)
    cost, pricing_source = estimate_cost(
        model_cfg, response.usage.prompt_tokens, response.usage.completion_tokens
    )

    return PipelineOutcome(
        status="success",
        content=out_check.text,
        provider=provider_kind,
        model=response.model or model_key,
        routing=routing_dict,
        latency_ms=response.latency_ms or int((time.perf_counter() - started) * 1000),
        usage={
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "estimated_cost_usd": cost,
            "cost_pricing_source": pricing_source,
            "pricing_available": cost is not None,
        },
        estimated_cost_usd=cost,
        cost_pricing_source=pricing_source,
        output_findings=out_findings,
        **{k: v for k, v in common.items() if k != "findings"},
        findings=findings,
    )
