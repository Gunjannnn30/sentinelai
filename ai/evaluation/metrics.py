"""Deterministic evaluation metrics.

All metrics are explainable and reproducible; each returns a dict with
``score`` (0..1 where sensible), ``value``, and a ``method`` name so the UI
can show *how* a number was produced.

- ``exact_match``       — normalized string equality
- ``token_similarity``  — Jaccard similarity over word tokens (reference-based)
- ``normalized_levenshtein`` — 1 - edit_distance/max_len (reference-based)
- ``policy_compliance`` — no policy/security violation occurred
- ``completion``        — call succeeded (no error)
- ``latency_ms``        — raw
- ``cost_usd``          — None when pricing unavailable

**Model-based judging**: *not implemented by default.* If enabled by an
operator it must be labelled a heuristic (see ``judge_enabled`` in reports);
one model's opinion is never ground truth.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def exact_match(output: str, expected: str) -> dict[str, Any]:
    if not expected:
        return {"score": None, "value": None, "method": "exact_match",
                "note": "no expected value provided"}
    eq = _normalize(output) == _normalize(expected)
    return {"score": 1.0 if eq else 0.0, "value": eq, "method": "exact_match"}


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(_normalize(text))


def token_similarity(output: str, reference: str) -> dict[str, Any]:
    a, b = set(_tokens(output)), set(_tokens(reference))
    if not a or not b:
        score = 1.0 if _normalize(output) == _normalize(reference) else 0.0
    else:
        score = len(a & b) / len(a | b)
    return {"score": round(score, 4), "value": round(score, 4), "method": "jaccard_token_similarity"}


def normalized_levenshtein(output: str, reference: str) -> dict[str, Any]:
    a, b = _normalize(output), _normalize(reference)
    if not a and not b:
        return {"score": 1.0, "value": 1.0, "method": "normalized_levenshtein"}
    if not a or not b:
        return {"score": 0.0, "value": 0.0, "method": "normalized_levenshtein"}
    if len(a) > 4000 or len(b) > 4000:  # guard cost
        return {"score": None, "value": None, "method": "normalized_levenshtein",
                "note": "input too long for edit distance"}
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    dist = prev[-1]
    score = 1 - dist / max(len(a), len(b))
    return {"score": round(max(0.0, score), 4), "value": dist, "method": "normalized_levenshtein"}


def policy_compliance(had_violation: bool) -> dict[str, Any]:
    return {"score": 0.0 if had_violation else 1.0, "value": not had_violation,
            "method": "policy_compliance"}


def completion_success(ok: bool) -> dict[str, Any]:
    return {"score": 1.0 if ok else 0.0, "value": ok, "method": "completion_rate"}


def evaluate_case(output: str, expected: str, reference: str, *,
                  had_violation: bool, ok: bool) -> dict[str, Any]:
    """Bundle the deterministic metrics for one (case, model) result."""
    ref = reference or expected
    metrics: dict[str, Any] = {
        "exact_match": exact_match(output, expected),
        "similarity": token_similarity(output, ref) if ref else
                      {"score": None, "value": None, "method": "jaccard_token_similarity",
                       "note": "no reference provided"},
        "edit_similarity": normalized_levenshtein(output, ref) if ref else
                           {"score": None, "value": None, "method": "normalized_levenshtein",
                            "note": "no reference provided"},
        "policy_compliance": policy_compliance(had_violation),
        "completion": completion_success(ok),
    }
    scored = [m["score"] for m in metrics.values() if isinstance(m.get("score"), int | float)]
    metrics["overall"] = {
        "score": round(sum(scored) / len(scored), 4) if scored else None,
        "value": round(sum(scored) / len(scored), 4) if scored else None,
        "method": "mean_of_available_deterministic_metrics",
        "note": "Model-based judging is NOT enabled; this aggregate is deterministic only.",
    }
    return metrics


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-model summary for a run (results = flattened records)."""
    by_model: dict[str, list[dict]] = {}
    for r in results:
        by_model.setdefault(r["model_key"], []).append(r)

    summary: dict[str, Any] = {"models": {}, "judge_enabled": False,
                               "scoring_note": "Deterministic metrics only (exact match, token "
                                               "similarity, edit similarity, policy compliance, "
                                               "completion). No LLM judge."}
    for model, rows in by_model.items():
        overalls = [row["metrics"].get("overall", {}).get("score")
                    for row in rows
                    if isinstance(row["metrics"].get("overall", {}).get("score"), int | float)]
        latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
        costs = [row["estimated_cost_usd"] for row in rows if row.get("estimated_cost_usd") is not None]
        errors = sum(1 for row in rows if row.get("status") != "success")
        summary["models"][model] = {
            "cases": len(rows),
            "avg_score": round(sum(overalls) / len(overalls), 4) if overalls else None,
            "completion_rate": round((len(rows) - errors) / len(rows), 4) if rows else None,
            "errors": errors,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "total_cost_usd": round(sum(costs), 6) if costs else None,
            "cost_available": bool(costs),
        }
    return summary


def regression_delta(baseline: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Compare avg_score per model vs a baseline run summary."""
    if not baseline:
        return {"available": False, "note": "No baseline run supplied."}
    out: dict[str, Any] = {"available": True, "models": {}}
    base_models = baseline.get("models", {})
    for model, stats in current.get("models", {}).items():
        base = base_models.get(model)
        if not base or base.get("avg_score") is None or stats.get("avg_score") is None:
            out["models"][model] = {"delta": None, "note": "baseline unavailable"}
            continue
        delta = round(stats["avg_score"] - base["avg_score"], 4)
        out["models"][model] = {
            "delta": delta,
            "baseline": base["avg_score"],
            "current": stats["avg_score"],
            "regressed": delta < -0.05,
        }
    return out
