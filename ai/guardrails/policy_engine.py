"""Declarative policy engine — deterministic, explainable, scope-aware.

A policy is a named rule with: enabled flag, severity, action
(allow|warn|mask|block), scope (organization | project | role), a list of
conditions, and a version.

Evaluation is a pure function over a :class:`EvaluationContext`; the result
names every condition that matched, so UI previews, dry-runs and the request
pipeline all produce the same explanation.

Fail-closed semantics: ``block`` always wins; then ``mask``; then ``warn``;
``allow`` never suppresses a stronger action from another matching policy.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any

ACTION_SEVERITY_ORDER = {"allow": 0, "warn": 1, "mask": 2, "block": 3}
VALID_ACTIONS = set(ACTION_SEVERITY_ORDER)


@dataclass
class PolicyRule:
    id: str
    name: str
    enabled: bool
    severity: str
    action: str
    scope: str = "organization"
    scope_role: str | None = None
    project_id: str | None = None
    version: int = 1
    conditions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_model(cls, p: Any) -> PolicyRule:
        return cls(
            id=p.id, name=p.name, enabled=p.enabled, severity=p.severity, action=p.action,
            scope=p.scope, scope_role=p.scope_role, project_id=p.project_id,
            version=p.version, conditions=list(p.conditions or []),
        )


@dataclass
class EvaluationContext:
    """Everything a condition may reference. Additive → easy to extend."""

    prompt: str = ""
    response: str = ""
    model: str | None = None
    provider: str | None = None
    project_id: str | None = None
    actor_role: str | None = None
    injection_categories: list[str] = field(default_factory=list)
    injection_score: int = 0
    injection_severity: str = "none"
    pii_types: list[str] = field(default_factory=list)
    masked_text: str | None = None   # set by the mask step for output policies

    def field_value(self, name: str) -> Any:
        return {
            "prompt_contains": self.prompt,
            "response_contains": self.response,
            "model": self.model,
            "provider": self.provider,
            "project_id": self.project_id,
            "actor_role": self.actor_role,
            "prompt_injection_category": self.injection_categories,
            "pii_type": self.pii_types,
            "prompt_length_over": len(self.prompt),
            "injection_score": self.injection_score,
        }.get(name)


@dataclass
class ConditionMatch:
    field: str
    op: str
    value: Any
    actual: Any
    matched: bool

    def as_dict(self) -> dict:
        # Do not echo large prompt content back — truncate for display.
        actual = self.actual
        if isinstance(actual, str) and len(actual) > 300:
            actual = actual[:300] + "…"
        return {
            "field": self.field, "op": self.op, "value": self.value,
            "actual": actual, "matched": self.matched,
        }


@dataclass
class PolicyDecision:
    policy_id: str | None
    policy_name: str
    action: str            # allow | warn | mask | block  (effective)
    severity: str
    matched: bool
    matched_conditions: list[dict] = field(default_factory=list)
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "action": self.action,
            "severity": self.severity,
            "matched": self.matched,
            "matched_conditions": self.matched_conditions,
            "explanation": self.explanation,
        }


def _condition_holds(cond: dict[str, Any], ctx: EvaluationContext) -> ConditionMatch:
    field_name = cond.get("field", "")
    op = cond.get("op", "equals")
    value = cond.get("value")
    actual = ctx.field_value(field_name)
    matched = False

    if actual is None and field_name not in ("model", "provider", "project_id", "actor_role"):
        actual = ""
    if field_name in ("prompt_contains", "response_contains"):
        text = actual or ""
        if op == "contains":
            matched = bool(value) and str(value).lower() in text.lower()
        elif op == "matches":
            try:
                matched = bool(re.search(str(value), text, re.IGNORECASE))
            except re.error:
                matched = False
        elif op == "equals":
            matched = text.strip() == str(value)
    elif field_name in ("prompt_injection_category", "pii_type"):
        items = list(actual or [])
        if op == "in":
            wanted = value if isinstance(value, list) else [value]
            matched = any(v in items for v in wanted)
        elif op == "equals":
            matched = str(value) in items
        elif op == "contains":
            matched = any(str(value) in i for i in items)
    elif field_name == "prompt_length_over":
        try:
            matched = int(actual or 0) > int(value)
        except (TypeError, ValueError):
            matched = False
    elif field_name == "injection_score":
        try:
            matched = int(actual or 0) >= int(value)
        except (TypeError, ValueError):
            matched = False
    else:  # scalar fields: model/provider/project_id/actor_role
        if op == "in":
            wanted = value if isinstance(value, list) else [value]
            matched = actual in wanted
        elif op == "contains":
            matched = bool(actual) and str(value) in str(actual)
        elif op == "matches":
            try:
                matched = bool(re.search(str(value), str(actual or ""), re.IGNORECASE))
            except re.error:
                matched = False
        else:
            matched = str(actual) == str(value)

    return ConditionMatch(field=field_name, op=op, value=value, actual=actual, matched=matched)


def _scope_applies(rule: PolicyRule, ctx: EvaluationContext) -> bool:
    if rule.scope == "organization" or not rule.scope:
        return True
    if rule.scope == "project":
        return rule.project_id is not None and rule.project_id == ctx.project_id
    if rule.scope == "role":
        return rule.scope_role is not None and rule.scope_role == ctx.actor_role
    return True


def evaluate_policies(rules: list[PolicyRule], ctx: EvaluationContext) -> list[PolicyDecision]:
    """Evaluate every rule; returns one decision per applicable rule."""
    decisions: list[PolicyDecision] = []
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.action not in VALID_ACTIONS:
            continue
        if not _scope_applies(rule, ctx):
            decisions.append(
                PolicyDecision(
                    policy_id=rule.id, policy_name=rule.name, action="allow",
                    severity=rule.severity, matched=False,
                    explanation=f"Out of scope (scope={rule.scope}).",
                )
            )
            continue
        if not rule.conditions:
            # An unconditional enabled policy always applies.
            decisions.append(
                PolicyDecision(
                    policy_id=rule.id, policy_name=rule.name, action=rule.action,
                    severity=rule.severity, matched=True,
                    explanation=f"Unconditional policy '{rule.name}' applied ({rule.action}).",
                )
            )
            continue
        matches = [_condition_holds(c, ctx) for c in rule.conditions]
        all_matched = all(m.matched for m in matches)
        matched_list = [m.as_dict() for m in matches if m.matched]
        decisions.append(
            PolicyDecision(
                policy_id=rule.id,
                policy_name=rule.name,
                action=rule.action if all_matched else "allow",
                severity=rule.severity,
                matched=all_matched,
                matched_conditions=matched_list,
                explanation=(
                    f"Policy '{rule.name}': {len(matched_list)}/{len(matches)} conditions matched "
                    f"→ action '{rule.action if all_matched else 'allow'}'."
                ),
            )
        )
    return decisions


def effective_action(decisions: list[PolicyDecision]) -> tuple[str, PolicyDecision | None]:
    """Combine decisions: block > mask > warn > allow. Returns (action, triggering)."""
    applicable = [d for d in decisions if d.matched and d.action in VALID_ACTIONS]
    if not applicable:
        return "allow", None
    best = max(applicable, key=lambda d: ACTION_SEVERITY_ORDER[d.action])
    if best.action == "allow":
        return "allow", None
    return best.action, best


def filter_rules_for_org(
    rules: list[PolicyRule], *, org_id: str, project_id: str | None, role: str
) -> list[PolicyRule]:
    """Narrow DB policies to those relevant for this request (cheap pre-filter)."""
    return [r for r in rules if _scope_applies(r, EvaluationContext(project_id=project_id, actor_role=role))]


def matches_glob(value: str, pattern: str) -> bool:
    return fnmatch.fnmatch(value.lower(), pattern.lower())
