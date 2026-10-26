# Evaluation

How SentinelAI measures model/gateway behavior. All scoring is
**deterministic** — this is stated explicitly in API responses
(`judge_enabled: false`); there is no LLM-as-judge and no fabricated scoring.

## Concepts

```
evaluation_datasets ──< evaluation_cases        (prompt, expected, reference, tags)
        │
        └─ evaluation_runs (name, model_keys[], baseline_run_id, status)
                 └─< evaluation_results (one row per case × model)
                           └─ metrics: JSON per case + run summary JSON
```

- **Dataset** — a named set of cases, created in one call (name, description,
  embedded `cases[]`, max 500). `is_synthetic` (on the response) labels demo
  datasets for the UI.
- **Case** — `prompt` (input), `expected` (exact expected output, optional),
  `reference` (a reference answer for similarity metrics, optional), `tags`.
- **Run** — executes a dataset against one or more `model_keys`, **through the
  full gateway pipeline** (same guardrails/routing/provider path as live
  traffic), producing one result per case × model.
- **Baseline** — an earlier run id; the new run stores a regression delta
  against it.

## Metrics (per case — `ai/evaluation/metrics.py`)

| Key | Method | Notes |
|---|---|---|
| `exact_match` | normalized string equality vs `expected` | `score: null` when no `expected` |
| `similarity` | Jaccard token similarity vs `reference` | `null` when no `reference` |
| `edit_similarity` | 1 − normalized Levenshtein vs `reference` | skipped for very long inputs |
| `policy_compliance` | 1.0 if the case's gateway outcome had no policy violation, else 0.0 | measures guardrail behavior, not just text |
| `completion` | 1.0 if the call succeeded, 0.0 for error/blocked | completion rate building block |
| `overall` | mean of available deterministic metrics | `note` states "model-based judging is NOT enabled" |

Each metric is a `{score, value, method, note?}` object — `null` score means
"not applicable", **not** a zero (important when averaging).

## Run summary (`evaluation_runs.summary`)

Per model: `cases`, `avg_score`, `completion_rate`, `errors`,
`avg_latency_ms`, `total_cost_usd`, `cost_available`. Top level: `models`,
`judge_enabled: false`, `scoring_note` (deterministic-metrics disclaimer).

**Regression delta** (when `baseline_run_id` given), per model:
`{delta, baseline, current, regressed}` — `regressed: true` when
`delta < -0.05`.

## API flow

```http
POST /api/v1/evals/datasets     {"name": "...", "description": "...",
                                 "cases": [{"prompt": "...", "expected": "...",
                                            "reference": "...", "tags": []}]}
GET  /api/v1/evals/datasets/{id}/cases
POST /api/v1/evals/runs         {"name": "baseline", "dataset_id": "...",
                                 "model_keys": ["sentinel-mock-small"]}
GET  /api/v1/evals/runs         ?dataset_id=...
GET  /api/v1/evals/runs/{run_id}          run + results + summary + regression
```

Minimum roles: reads `viewer`, creating datasets/runs `developer`.

## Honest constraints

- **Scoring is deterministic only**: exact match, token similarity, edit
  similarity, policy compliance, completion. Semantic quality ("is this a
  good answer?") is not measured — by design, not by omission: a fake judge
  would fabricate judgments.
- **Cost/latency only when known**: `cost_available` is false unless pricing
  metadata exists on the model config (demo model rows carry pricing labeled
  `pricing_source`).
- **Mock provider**: local runs without provider keys score the deterministic
  mock outputs — fine for pipeline/guardrail regression testing, not for
  model-quality benchmarking.
- Cases run sequentially through the pipeline (bounded by dataset size);
  there is no distributed execution yet.

## What is covered by tests

`backend/tests/` pins the metric math (exact/similarity/edit/compliance/
overall aggregation, `null`-metric handling), summary statistics, and
regression deltas (`regressed` threshold), plus an end-to-end dataset → run →
results flow against the mock provider.
