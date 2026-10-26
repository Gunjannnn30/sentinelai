import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatResult } from "./chat-result";
import type { ChatCompletionOut } from "@/lib/types";

function result(overrides: Partial<ChatCompletionOut>): ChatCompletionOut {
  return {
    request_id: "req-1",
    status: "success",
    policy_outcome: "allow",
    model: "gpt-4o-mini",
    provider: "openai",
    content: "Hello there.",
    latency_ms: 950,
    usage: {
      prompt_tokens: 10,
      completion_tokens: 20,
      total_tokens: 30,
      estimated_cost_usd: 0.00042,
      cost_pricing_source: "manual",
      pricing_available: true,
    },
    findings: [],
    route_explanation: "routed to openai by priority",
    error: null,
    demo: false,
    ...overrides,
  };
}

describe("ChatResult", () => {
  it("renders the model content on success", () => {
    render(<ChatResult result={result({})} />);
    expect(screen.getByText("Hello there.")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o-mini")).toBeInTheDocument();
  });

  it("renders the blocked reason without fabricating content", () => {
    render(
      <ChatResult
        result={result({ status: "blocked", policy_outcome: "block", content: null, error: { blocked_reason: "Prompt injection detected." } })}
      />,
    );
    expect(screen.getByText("Prompt injection detected.")).toBeInTheDocument();
    expect(screen.queryByText("Hello there.")).toBeNull();
    expect(screen.getByText("blocked")).toBeInTheDocument();
  });

  it("renders the gateway error message and marks demo data", () => {
    render(
      <ChatResult
        result={result({ status: "error", content: null, demo: true, error: { category: "provider_timeout", message: "Upstream timed out.", retryable: true } })}
      />,
    );
    expect(screen.getByText("Upstream timed out.")).toBeInTheDocument();
    expect(screen.getByText("Simulated / demo data")).toBeInTheDocument();
  });

  it("shows Unavailable when pricing is missing", () => {
    render(
      <ChatResult
        result={result({
          usage: {
            prompt_tokens: null,
            completion_tokens: null,
            total_tokens: null,
            estimated_cost_usd: null,
            cost_pricing_source: null,
            pricing_available: false,
          },
        })}
      />,
    );
    // Both cost and tokens fall back to the literal "Unavailable" — no guessed numbers.
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });
});
