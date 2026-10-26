import { describe, expect, it } from "vitest";
import { applyClientFilters, EMPTY_FILTERS, type RequestFilters } from "./requests-table";
import type { RequestOut } from "@/lib/types";

function row(overrides: Partial<RequestOut>): RequestOut {
  return {
    id: "req-0001",
    org_id: "org-1",
    project_id: null,
    status: "success",
    policy_outcome: "allow",
    provider_kind: "openai",
    model_key: "gpt-4o-mini",
    route_explanation: null,
    latency_ms: 800,
    prompt_tokens: 10,
    completion_tokens: 20,
    total_tokens: 30,
    estimated_cost_usd: 0.001,
    cost_pricing_source: "manual",
    error_category: null,
    error_message: null,
    blocked_reason: null,
    prompt_chars: 12,
    response_chars: 34,
    has_content: true,
    actor_email: "dev@example.com",
    created_at: "2026-01-01T00:00:00Z",
    is_demo_data: false,
    ...overrides,
  };
}

const items: RequestOut[] = [
  row({ id: "req-aaa1" }),
  row({ id: "req-bbb2", status: "blocked", policy_outcome: "block", model_key: "claude-3", blocked_reason: "injection" }),
  row({ id: "req-ccc3", status: "error", error_category: "provider_timeout", model_key: "llama-3" }),
  row({ id: "req-ddd4", status: "success", model_key: "gpt-4o", is_demo_data: true }),
];

describe("applyClientFilters", () => {
  it("returns everything with empty filters", () => {
    expect(applyClientFilters(items, EMPTY_FILTERS)).toHaveLength(4);
  });

  it("filters by status", () => {
    const out = applyClientFilters(items, { ...EMPTY_FILTERS, status: "blocked" });
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe("req-bbb2");
  });

  it("filters by policy outcome", () => {
    const out = applyClientFilters(items, { ...EMPTY_FILTERS, policyOutcome: "block" });
    expect(out.map((r) => r.id)).toEqual(["req-bbb2"]);
  });

  it("filters by model key", () => {
    const out = applyClientFilters(items, { ...EMPTY_FILTERS, model: "gpt-4o" });
    expect(out.map((r) => r.id)).toEqual(["req-ddd4"]);
  });

  it("filters by error category", () => {
    const out = applyClientFilters(items, { ...EMPTY_FILTERS, errorCategory: "provider_timeout" });
    expect(out.map((r) => r.id)).toEqual(["req-ccc3"]);
  });

  it("matches the request ID case-insensitively", () => {
    const out = applyClientFilters(items, { ...EMPTY_FILTERS, q: "REQ-BBB" });
    expect(out.map((r) => r.id)).toEqual(["req-bbb2"]);
  });

  it("combines filters", () => {
    const filters: RequestFilters = { ...EMPTY_FILTERS, status: "success", model: "gpt-4o" };
    expect(applyClientFilters(items, filters).map((r) => r.id)).toEqual(["req-ddd4"]);
  });

  it("returns an empty array when nothing matches", () => {
    expect(applyClientFilters(items, { ...EMPTY_FILTERS, q: "nope" })).toEqual([]);
  });
});
