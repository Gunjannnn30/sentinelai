"use client";

// Analytics live under /api/v1/analytics/* (router prefix), not /api/v1/*.
import { PageHeader } from "@/components/page-header";
import { DemoBadge } from "@/components/demo-badge";
import { ErrorBanner } from "@/components/error-banner";
import { BarChartView, TimeseriesChart, type ChartColumn } from "@/components/charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useApi } from "@/hooks/use-api";
import { API_V1 } from "@/lib/api";
import type {
  AnalyticsOut,
  CostBreakdownRow,
  ModelAnalyticsOut,
  SecurityAnalyticsOut,
} from "@/lib/types";
import { money, ms, num, pct } from "@/lib/format";

const costColumn: ChartColumn<CostBreakdownRow> = {
  key: "cost_usd",
  label: "Cost (USD)",
  value: (r) => r.cost_usd,
  format: (r) => (r.pricing_available ? money(r.cost_usd) : "Unavailable"),
  color: "#6366f1",
};

export default function AnalyticsPage() {
  const costs = useApi<AnalyticsOut>(`${API_V1}/analytics/costs`);
  const security = useApi<SecurityAnalyticsOut>(`${API_V1}/analytics/security`);
  const models = useApi<ModelAnalyticsOut>(`${API_V1}/analytics/models`);

  const loading = costs.loading || security.loading || models.loading;
  const error = costs.error ?? security.error ?? models.error;

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <PageHeader title="Analytics" description="Spend, model health, and guardrail activity." />
        <ErrorBanner error={error} onRetry={() => { costs.refetch(); security.refetch(); models.refetch(); }} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Spend, model health, and guardrail activity."
        actions={<DemoBadge isDemo={Boolean(models.data?.demo_data_included)} />}
      />

      {costs.data ? (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Metric label="Month to date" value={money(costs.data.month_to_date_usd)} />
            <Metric
              label="Monthly budget"
              value={costs.data.budget_monthly_usd ? `$${costs.data.budget_monthly_usd}` : "No budget set"}
            />
            <Metric label="Pricing note" value={costs.data.pricing_source_note || "—"} small />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Daily spend</CardTitle>
            </CardHeader>
            <CardContent>
              <TimeseriesChart
                title="Daily spend (USD)"
                rows={costs.data.daily}
                series={[
                  {
                    key: "cost_usd",
                    label: "Cost",
                    value: (r) => r.cost_usd,
                    format: (r) => (r.pricing_available ? money(r.cost_usd) : "Unavailable"),
                    color: "#6366f1",
                  },
                ]}
              />
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Cost by provider</CardTitle>
              </CardHeader>
              <CardContent>
                {costs.data.by_provider.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No provider traffic yet.</p>
                ) : (
                  <BarChartView
                    title="Cost by provider"
                    rows={costs.data.by_provider}
                    column={costColumn}
                    horizontal
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Cost by model</CardTitle>
              </CardHeader>
              <CardContent>
                {costs.data.by_model.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No model traffic yet.</p>
                ) : (
                  <BarChartView
                    title="Cost by model"
                    rows={costs.data.by_model}
                    column={costColumn}
                    horizontal
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <EmptyState title="No cost data yet." description="Costs appear once requests flow through the gateway." />
      )}

      {security.data ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Security activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-4">
              <Metric label="Blocked requests" value={num(security.data.blocked_requests)} />
              <Metric label="Injection detections" value={num(security.data.injection_detections)} />
              <Metric label="PII masking events" value={num(security.data.pii_masking_events)} />
              <Metric label="Policy violations" value={num(security.data.policy_violations)} />
            </div>
            {security.data.top_rules.length > 0 ? (
              <div>
                <h4 className="mb-2 text-sm font-medium">Top rules</h4>
                <ul className="space-y-1 text-sm">
                  {security.data.top_rules.map((rule) => (
                    <li key={rule.rule} className="flex justify-between rounded-md border p-2">
                      <span className="font-mono text-xs">{rule.rule}</span>
                      <span className="text-muted-foreground">
                        {num(rule.count)} · {rule.severity}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {security.data.series.length > 0 ? (
              <TimeseriesChart
                title="Security events per day"
                rows={security.data.series}
                series={[
                  { key: "prompt_injection", label: "Injection", value: (r) => r.prompt_injection, format: (r) => num(r.prompt_injection), color: "#ef4444" },
                  { key: "pii_detected", label: "PII", value: (r) => r.pii_detected, format: (r) => num(r.pii_detected), color: "#f59e0b" },
                  { key: "policy_violation", label: "Policy", value: (r) => r.policy_violation, format: (r) => num(r.policy_violation), color: "#8b5cf6" },
                ]}
              />
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {models.data ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Model health</CardTitle>
          </CardHeader>
          <CardContent>
            {models.data.rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No model traffic yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="px-2 py-2">Model</th>
                      <th className="px-2 py-2">Provider</th>
                      <th className="px-2 py-2">Requests</th>
                      <th className="px-2 py-2">Errors</th>
                      <th className="px-2 py-2">Error rate</th>
                      <th className="px-2 py-2">Avg latency</th>
                      <th className="px-2 py-2">p95</th>
                      <th className="px-2 py-2">Tokens</th>
                      <th className="px-2 py-2">Est. cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.data.rows.map((row) => (
                      <tr key={row.model_key} className="border-b last:border-0">
                        <td className="px-2 py-2 font-medium">{row.model_key}</td>
                        <td className="px-2 py-2">{row.provider_kind}</td>
                        <td className="px-2 py-2">{num(row.requests)}</td>
                        <td className="px-2 py-2">{num(row.errors)}</td>
                        <td className="px-2 py-2">{pct(row.error_rate)}</td>
                        <td className="px-2 py-2">{ms(row.avg_latency_ms)}</td>
                        <td className="px-2 py-2">{ms(row.p95_latency_ms)}</td>
                        <td className="px-2 py-2">{num(row.total_tokens)}</td>
                        <td className="px-2 py-2">
                          {row.pricing_available ? money(row.est_cost_usd) : "Unavailable"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  small,
}: {
  label: string;
  value: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={small ? "mt-1 text-sm" : "mt-1 text-2xl font-bold"}>{value}</p>
    </div>
  );
}
