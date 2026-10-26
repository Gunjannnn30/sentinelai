"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner } from "@/components/error-banner";
import { DemoBadge } from "@/components/demo-badge";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useApi } from "@/hooks/use-api";
import { API_V1 } from "@/lib/api";
import type { RequestDetailOut } from "@/lib/types";
import { dateTime, money, ms, num } from "@/lib/format";

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const { data, error, loading, refetch } = useApi<RequestDetailOut>(
    params?.id ? `${API_V1}/requests/${params.id}` : null,
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) return <ErrorBanner error={error} onRetry={refetch} />;

  if (!data) {
    return (
      <EmptyState
        title="Request not found."
        action={
          <Link href="/requests" className="text-sm text-primary underline underline-offset-2">
            Back to requests
          </Link>
        }
      />
    );
  }

  return (
    <div>
      <PageHeader
        title={`Request ${data.id.slice(0, 8)}…`}
        description={dateTime(data.created_at)}
        actions={<DemoBadge isDemo={data.is_demo_data} />}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Status" value={<StatusBadge value={data.status} />} />
              <Field label="Policy outcome" value={<StatusBadge value={data.policy_outcome} />} />
              <Field label="Model" value={data.model_key ?? "—"} />
              <Field label="Provider" value={data.provider_kind ?? "—"} />
              <Field label="Latency" value={ms(data.latency_ms)} />
              <Field label="Actor" value={data.actor_email ?? "—"} />
              <Field label="Project" value={data.project_id ?? "—"} />
              <Field label="Full request ID" value={<span className="font-mono text-xs">{data.id}</span>} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Usage &amp; cost</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Prompt tokens" value={num(data.prompt_tokens)} />
              <Field label="Completion tokens" value={num(data.completion_tokens)} />
              <Field label="Total tokens" value={num(data.total_tokens)} />
              <Field
                label="Estimated cost"
                value={
                  <>
                    {money(data.estimated_cost_usd)}
                    {!data.cost_pricing_source ? (
                      <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">
                        (pricing unavailable)
                      </span>
                    ) : null}
                  </>
                }
              />
              <Field
                label="Pricing source"
                value={data.cost_pricing_source ?? "Unavailable"}
              />
              <Field
                label="Chars"
                value={`${num(data.prompt_chars)} in / ${num(data.response_chars)} out`}
              />
            </dl>
          </CardContent>
        </Card>
      </div>

      {data.route_explanation || data.error_category || data.blocked_reason ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">Outcome detail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {data.route_explanation ? (
              <p>
                <span className="font-medium">Routing:</span> {data.route_explanation}
              </p>
            ) : null}
            {data.error_category ? (
              <p>
                <span className="font-medium">Error category:</span> {data.error_category}
              </p>
            ) : null}
            {data.error_message ? (
              <p>
                <span className="font-medium">Error:</span> {data.error_message}
              </p>
            ) : null}
            {data.blocked_reason ? (
              <p>
                <span className="font-medium">Blocked:</span> {data.blocked_reason}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">
            Security timeline ({data.security_events.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.security_events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No security events recorded for this request.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.security_events.map((event) => (
                <li key={event.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{event.rule_name}</span>
                    <StatusBadge value={event.severity} />
                    <Badgeish label={event.category} />
                    <Badgeish label={event.action_taken} />
                    <span className="ml-auto text-xs text-muted-foreground">
                      {dateTime(event.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{event.detail}</p>
                  {event.masked_types.length > 0 ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Masked: {event.masked_types.join(", ")}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
    </div>
  );
}

function Badgeish({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{label}</span>
  );
}
