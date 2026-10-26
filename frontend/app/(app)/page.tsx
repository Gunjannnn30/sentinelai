"use client";

import { PageHeader } from "@/components/page-header";
import { DemoBadge } from "@/components/demo-badge";
import { ErrorBanner } from "@/components/error-banner";
import { TimeseriesChart } from "@/components/charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useApi } from "@/hooks/use-api";
import { API_V1 } from "@/lib/api";
import type { OverviewOut } from "@/lib/types";
import { money, ms, num, pct } from "@/lib/format";

export default function OverviewPage() {
  const { data, error, loading, refetch } = useApi<OverviewOut>(
    `${API_V1}/analytics/overview`,
  );

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Traffic, outcomes, and spend for the last 30 days."
        actions={data?.demo_data_included ? <DemoBadge isDemo /> : null}
      />

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : !data ? (
        <EmptyState title="No data yet." description="Send a request from the Playground to get started." />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total requests" value={num(data.total_requests)} />
            <StatCard label="Successful" value={num(data.successful_requests)} />
            <StatCard label="Blocked" value={num(data.blocked_requests)} />
            <StatCard label="Errors" value={num(data.error_requests)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Avg latency" value={ms(data.avg_latency_ms)} />
            <StatCard
              label="Estimated spend"
              value={
                data.spend_pricing_available
                  ? money(data.estimated_spend_usd)
                  : "Unavailable"
              }
              note={data.spend_pricing_available ? undefined : "Pricing not configured"}
            />
            <StatCard label="Policy pass rate" value={pct(data.policy_pass_rate)} />
            <StatCard label="Unique models" value={num(data.unique_models)} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Requests per day</CardTitle>
            </CardHeader>
            <CardContent>
              <TimeseriesChart
                title="Requests per day"
                rows={data.series}
                series={[
                  { key: "total", label: "Total", value: (r) => r.total, format: (r) => num(r.total), color: "#64748b" },
                  { key: "success", label: "Success", value: (r) => r.success, format: (r) => num(r.success), color: "#10b981" },
                  { key: "blocked", label: "Blocked", value: (r) => r.blocked, format: (r) => num(r.blocked), color: "#f59e0b" },
                  { key: "error", label: "Error", value: (r) => r.error, format: (r) => num(r.error), color: "#ef4444" },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-bold">{value}</p>
        {note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}
      </CardContent>
    </Card>
  );
}
