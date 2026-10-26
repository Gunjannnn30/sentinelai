"""Deterministic, explainable model routing.

Order of operations (each step appends a human-readable trace):

1. **Policy allowlist** — start from the org's enabled model configs.
2. **Capability gate** — model must advertise the required capability.
3. **Organization/project policy** — never route to a model whose selection
   would violate a policy condition; a model explicitly blocked by policy is
   removed from candidates.
4. **Cost preference** — drop models above an admin cost ceiling when a
   cheaper compliant option exists.
5. **Latency preference** — respect an admin latency constraint.
6. **Admin priority** — explicit ``priority`` (lower = preferred) wins ties,
   then price, then latency class.

If no compliant model survives → **fail closed** (``RoutingResult.selected is None``).
No ML: every decision is reproducible from the inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PREFERRED_ORDER = {"fast": 0, "medium": 1, "slow": 2}


@dataclass
class Candidate:
    model_key: str
    provider_kind: str
    display_name: str
    capabilities: list[str] = field(default_factory=list)
    priority: int = 100
    latency_class: str = "medium"
    input_cost_per_1m: float | None = None
    output_cost_per_1m: float | None = None
    pricing_source: str | None = None
    enabled: bool = True


@dataclass
class RoutingConstraints:
    capability: str = "chat"
    max_input_cost_per_1m: float | None = None
    max_latency_class: str | None = None      # fast | medium | slow
    preferred_model: str | None = None        # explicit user/admin pin
    exclude_models: list[str] = field(default_factory=list)  # policy-forced exclusions


@dataclass
class RoutingResult:
    selected: Candidate | None
    explanation: str
    trace: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)  # {model, reason}

    @property
    def ok(self) -> bool:
        return self.selected is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.model_key if self.selected else None,
            "provider": self.selected.provider_kind if self.selected else None,
            "explanation": self.explanation,
            "trace": self.trace,
            "rejected": self.rejected,
        }


def _cost(c: Candidate) -> float:
    return (c.input_cost_per_1m or 0.0) + 2.0 * (c.output_cost_per_1m or 0.0)


def route(
    candidates: list[Candidate],
    constraints: RoutingConstraints | None = None,
) -> RoutingResult:
    cons = constraints or RoutingConstraints()
    trace: list[str] = []
    rejected: list[dict[str, str]] = []

    working = [c for c in candidates if c.enabled]
    trace.append(
        f"Start: {len(working)}/{len(candidates)} enabled model(s)."
    )
    for c in candidates:
        if not c.enabled:
            rejected.append({"model": c.model_key, "reason": "disabled"})

    def drop(predicate, reason_fmt) -> None:
        nonlocal working
        kept = []
        for c in working:
            if predicate(c):
                kept.append(c)
            else:
                rejected.append({"model": c.model_key, "reason": reason_fmt(c)})
        working = kept

    # 1. explicit pin (must still pass all gates below)
    if cons.preferred_model:
        trace.append(f"Explicit preference: '{cons.preferred_model}' (still subject to policy gates).")

    # 2. policy exclusions — fail-closed input, never bypassed
    if cons.exclude_models:
        drop(lambda c: c.model_key not in cons.exclude_models,
             lambda c: "excluded by organization policy")
        trace.append(f"Policy exclusions removed models: {cons.exclude_models or '[]'} "
                     f"→ {len(working)} remain.")

    # 3. capability
    drop(lambda c: cons.capability in (c.capabilities or []),
         lambda c: f"missing capability '{cons.capability}'")
    trace.append(f"Capability gate ('{cons.capability}') → {len(working)} remain.")

    # 4. admin cost ceiling (only when a cheaper compliant option exists)
    if cons.max_input_cost_per_1m is not None:
        affordable = [c for c in working if (c.input_cost_per_1m or 0.0) <= cons.max_input_cost_per_1m]
        if affordable:
            drop(lambda c: (c.input_cost_per_1m or 0.0) <= cons.max_input_cost_per_1m,
                 lambda c: f"input cost {c.input_cost_per_1m}/1M exceeds ceiling "
                           f"{cons.max_input_cost_per_1m}/1M")
            trace.append(f"Cost ceiling {cons.max_input_cost_per_1m}/1M → {len(working)} remain.")
        else:
            trace.append("Cost ceiling applied but no model is under it — ceiling waived "
                         "(availability preferred over silent failure); cheapest options ranked first.")

    # 5. latency constraint
    if cons.max_latency_class:
        limit = PREFERRED_ORDER.get(cons.max_latency_class, 2)
        within = [c for c in working if PREFERRED_ORDER.get(c.latency_class, 1) <= limit]
        if within:
            drop(lambda c: PREFERRED_ORDER.get(c.latency_class, 1) <= limit,
                 lambda c: f"latency class '{c.latency_class}' exceeds "
                           f"'{cons.max_latency_class}'")
            trace.append(f"Latency constraint ≤ {cons.max_latency_class} → {len(working)} remain.")

    if not working:
        explanation = (
            "FAIL CLOSED: no compliant model available after policy, capability, cost and "
            "latency gates. Nothing was routed and no provider was called."
        )
        trace.append(explanation)
        return RoutingResult(selected=None, explanation=explanation, trace=trace, rejected=rejected)

    # 6. ranking
    ranked = sorted(
        working,
        key=lambda c: (
            0 if (cons.preferred_model and c.model_key == cons.preferred_model) else 1,
            c.priority,
            _cost(c),
            PREFERRED_ORDER.get(c.latency_class, 1),
            c.model_key,
        ),
    )
    winner = ranked[0]
    trace.append(
        "Ranked by: explicit pin > admin priority > blended cost > latency class. "
        f"Candidate order: {[c.model_key for c in ranked[:5]]}."
    )
    if cons.preferred_model and winner.model_key != cons.preferred_model:
        trace.append(
            f"Preferred model '{cons.preferred_model}' was not selected — it failed a gate or "
            f"another model ranks higher."
        )
    price = (
        f"${winner.input_cost_per_1m}/1M in, ${winner.output_cost_per_1m}/1M out"
        if winner.input_cost_per_1m is not None
        else "pricing unavailable"
    )
    explanation = (
        f"Selected '{winner.model_key}' ({winner.provider_kind}): priority {winner.priority}, "
        f"latency class {winner.latency_class}, {price}. "
        f"{len(ranked) - 1} other compliant candidate(s) available."
    )
    return RoutingResult(selected=winner, explanation=explanation, trace=trace, rejected=rejected)
