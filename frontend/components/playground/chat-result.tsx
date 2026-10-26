"use client";

// Renders one ChatCompletionOut. The gateway always answers HTTP 200, so this
// component — not the fetch layer — decides how success / blocked / error are
// shown. Never fabricates content when status !== "success".
import type { ChatCompletionOut } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DemoBadge } from "@/components/demo-badge";
import { StatusBadge } from "@/components/status-badge";
import { money, ms, num, truncate } from "@/lib/format";

export function ChatResult({ result }: { result: ChatCompletionOut }) {
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">
          {result.status === "success"
            ? "Response"
            : result.status === "blocked"
              ? "Blocked by policy"
              : "Request failed"}
        </CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge value={result.status} />
          <Badge variant="outline">{result.policy_outcome}</Badge>
          <DemoBadge isDemo={result.demo} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.status === "success" ? (
          result.content !== null && result.content !== "" ? (
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-4 text-sm">
              {result.content}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">
              The model returned success but no content.
            </p>
          )
        ) : null}

        {result.status === "blocked" ? (
          <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
            <p className="text-sm font-medium text-destructive">
              {result.error?.blocked_reason ??
                `The request was blocked by policy (${result.policy_outcome}).`}
            </p>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              request_id: {result.request_id}
            </p>
          </div>
        ) : null}

        {result.status === "error" ? (
          <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
            <p className="text-sm font-medium text-destructive">
              {result.error?.message ??
                result.error?.category ??
                "The gateway reported an error for this request."}
            </p>
            {result.error?.retryable !== undefined ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {result.error.retryable ? "Retryable." : "Not retryable."}
              </p>
            ) : null}
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              request_id: {result.request_id}
            </p>
          </div>
        ) : null}

        {result.findings.length > 0 ? (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Security findings</h4>
            <ul className="space-y-1">
              {result.findings.map((finding, i) => (
                <li key={i} className="rounded-md border p-2 text-sm">
                  <span className="font-medium">{finding.rule_name || finding.category}</span>
                  <Badge variant="secondary" className="ml-2">
                    {finding.severity}
                  </Badge>
                  <p className="mt-1 text-muted-foreground">
                    {truncate(finding.detail, 200)}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {result.route_explanation ? (
          <p className="text-xs text-muted-foreground">{result.route_explanation}</p>
        ) : null}

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
          <div>
            <dt>Model</dt>
            <dd className="font-medium text-foreground">{result.model ?? "—"}</dd>
          </div>
          <div>
            <dt>Provider</dt>
            <dd className="font-medium text-foreground">{result.provider ?? "—"}</dd>
          </div>
          <div>
            <dt>Latency</dt>
            <dd className="font-medium text-foreground">{ms(result.latency_ms)}</dd>
          </div>
          <div>
            <dt>
              Cost{" "}
              {!result.usage.pricing_available ? (
                <span className="text-amber-600 dark:text-amber-400">(unavailable)</span>
              ) : null}
            </dt>
            <dd className="font-medium text-foreground">
              {money(result.usage.estimated_cost_usd)}
            </dd>
          </div>
          <div>
            <dt>Tokens</dt>
            <dd className="font-medium text-foreground">
              {num(result.usage.total_tokens)}
            </dd>
          </div>
          <div>
            <dt>Request ID</dt>
            <dd className="font-mono text-[11px]">{result.request_id}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

export function ChatPending() {
  return <p className="text-sm text-muted-foreground">Waiting for the model…</p>;
}
