"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner } from "@/components/error-banner";
import { DemoBadge } from "@/components/demo-badge";
import {
  applyClientFilters,
  EMPTY_FILTERS,
  RequestsTable,
  type RequestFilters,
} from "@/components/requests/requests-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useApi } from "@/hooks/use-api";
import { API_V1, qs } from "@/lib/api";
import type { RequestPage } from "@/lib/types";
import { num } from "@/lib/format";

const STATUSES = ["success", "blocked", "error"];
const OUTCOMES = ["allow", "warn", "block"];

export default function RequestsPage() {
  const [filters, setFilters] = useState<RequestFilters>(EMPTY_FILTERS);
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  // Server-side filtering via the documented query params; the table component
  // additionally applies applyClientFilters over the fetched page.
  const path = useMemo(
    () =>
      `${API_V1}/requests${qs({
        q: filters.q,
        status: filters.status,
        policy_outcome: filters.policyOutcome,
        model: filters.model,
        error_category: filters.errorCategory,
        days,
        page,
        page_size: pageSize,
      })}`,
    [filters, days, page],
  );

  const { data, error, loading, refetch } = useApi<RequestPage>(path);

  const rows = useMemo(
    () => (data ? applyClientFilters(data.items, filters) : []),
    [data, filters],
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const anyDemo = rows.some((r) => r.is_demo_data);

  return (
    <div>
      <PageHeader
        title="Requests"
        description="Every gateway call, its policy outcome, and its cost."
        actions={
          <div className="flex items-center gap-2">
            {anyDemo ? <DemoBadge isDemo /> : null}
            <Label htmlFor="req-days" className="sr-only">
              Time range
            </Label>
            <Select
              id="req-days"
              value={String(days)}
              onChange={(e) => {
                setDays(Number(e.target.value));
                setPage(1);
              }}
              className="w-36"
            >
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </Select>
          </div>
        }
      />

      <div className="mb-4 grid gap-3 md:grid-cols-5">
        <div className="grid gap-1.5">
          <Label htmlFor="f-q">Search</Label>
          <Input
            id="f-q"
            placeholder="Model, actor, error…"
            value={filters.q}
            onChange={(e) => {
              setFilters((f) => ({ ...f, q: e.target.value }));
              setPage(1);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="f-status">Status</Label>
          <Select
            id="f-status"
            value={filters.status}
            onChange={(e) => {
              setFilters((f) => ({ ...f, status: e.target.value }));
              setPage(1);
            }}
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="f-outcome">Policy outcome</Label>
          <Select
            id="f-outcome"
            value={filters.policyOutcome}
            onChange={(e) => {
              setFilters((f) => ({ ...f, policyOutcome: e.target.value }));
              setPage(1);
            }}
          >
            <option value="">All</option>
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="f-model">Model</Label>
          <Input
            id="f-model"
            placeholder="model_key"
            value={filters.model}
            onChange={(e) => {
              setFilters((f) => ({ ...f, model: e.target.value }));
              setPage(1);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="f-error">Error category</Label>
          <Input
            id="f-error"
            placeholder="e.g. provider_timeout"
            value={filters.errorCategory}
            onChange={(e) => {
              setFilters((f) => ({ ...f, errorCategory: e.target.value }));
              setPage(1);
            }}
          />
        </div>
      </div>

      {loading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No requests match."
          description="Adjust the filters or send a message from the Playground."
          action={
            <Link href="/playground" className="text-sm text-primary underline underline-offset-2">
              Open Playground
            </Link>
          }
        />
      ) : (
        <>
          <RequestsTable items={rows} />
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {num(rows.length)} of {num(data?.total ?? 0)} requests
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span>
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
