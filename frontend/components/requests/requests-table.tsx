"use client";

// Client-side filtering layer on top of the server query. The backend already
// supports q/status/policy_outcome/model/error_category/days; this hook keeps
// the URL-independent UI state and exposes applyClientFilters for tests.
import type { RequestOut } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/status-badge";
import { DemoBadge } from "@/components/demo-badge";
import { dateTime, money, ms, num, truncate } from "@/lib/format";

export interface RequestFilters {
  q: string;
  status: string;
  policyOutcome: string;
  model: string;
  errorCategory: string;
}

export const EMPTY_FILTERS: RequestFilters = {
  q: "",
  status: "",
  policyOutcome: "",
  model: "",
  errorCategory: "",
};

/** Pure filter over already-fetched rows.
 *
 * Mirrors the server contract (backend/app/api/v1/requests_api.py): `q`
 * matches the request ID; the other filters are exact-match dropdowns. The
 * substring check on `id` is a superset of the server's prefix match, so it
 * never hides a row the server returned for the same query.
 */
export function applyClientFilters(
  items: RequestOut[],
  filters: RequestFilters,
): RequestOut[] {
  const q = filters.q.trim().toLowerCase();
  return items.filter((item) => {
    if (filters.status && item.status !== filters.status) return false;
    if (filters.policyOutcome && item.policy_outcome !== filters.policyOutcome)
      return false;
    if (filters.model && item.model_key !== filters.model) return false;
    if (filters.errorCategory && item.error_category !== filters.errorCategory)
      return false;
    if (!q) return true;
    return item.id.toLowerCase().includes(q);
  });
}

export function RequestsTable({ items }: { items: RequestOut[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Provider</TableHead>
          <TableHead>Policy</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Latency</TableHead>
          <TableHead>Tokens</TableHead>
          <TableHead>Cost</TableHead>
          <TableHead>Actor</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell>
              <a
                className="text-primary underline underline-offset-2"
                href={`/requests/${item.id}`}
              >
                {dateTime(item.created_at)}
              </a>
              <DemoBadge isDemo={item.is_demo_data} className="ml-2" />
            </TableCell>
            <TableCell>
              <a
                className="text-primary underline underline-offset-2"
                href={`/requests/${item.id}`}
              >
                {item.model_key ?? "—"}
              </a>
            </TableCell>
            <TableCell>{item.provider_kind ?? "—"}</TableCell>
            <TableCell>
              <StatusBadge value={item.policy_outcome} />
              {item.blocked_reason ? (
                <p className="mt-1 max-w-[16rem] text-xs text-muted-foreground">
                  {truncate(item.blocked_reason, 80)}
                </p>
              ) : null}
            </TableCell>
            <TableCell>
              <StatusBadge value={item.status} />
              {item.error_category ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.error_category}
                </p>
              ) : null}
            </TableCell>
            <TableCell>{ms(item.latency_ms)}</TableCell>
            <TableCell>{num(item.total_tokens)}</TableCell>
            <TableCell>{money(item.estimated_cost_usd)}</TableCell>
            <TableCell className="text-xs">{item.actor_email ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
