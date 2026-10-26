"use client";

// GET /admin/audit (developer+) returns {total, limit, offset, items};
// export + verify are admin-only.
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner, errorText, requestIdOf } from "@/components/error-banner";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch, qs } from "@/lib/api";
import type { AuditPage, AuditVerifyOut } from "@/lib/types";
import { canAdmin } from "@/lib/role";
import { dateTime } from "@/lib/format";

const LIMIT = 25;

export default function AuditPage() {
  const { me } = useAuth();
  const { toast } = useToast();
  const isAdmin = canAdmin(me?.role);

  const [filters, setFilters] = useState({ eventType: "", resourceType: "", outcome: "" });
  const [offset, setOffset] = useState(0);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyOut | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  const path = `${API_V1}/admin/audit${qs({
    limit: LIMIT,
    offset,
    event_type: filters.eventType,
    resource_type: filters.resourceType,
    outcome: filters.outcome,
  })}`;
  const { data, error, loading, refetch } = useApi<AuditPage>(path);

  const verify = async () => {
    setVerifying(true);
    try {
      const out = await apiFetch<AuditVerifyOut>(`${API_V1}/admin/audit/verify`);
      setVerifyResult(out);
    } catch (err) {
      toast({ title: "Verify failed", description: errorText(err), variant: "destructive", requestId: requestIdOf(err) });
    } finally {
      setVerifying(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / LIMIT)) : 1;
  const page = Math.floor(offset / LIMIT) + 1;

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="Append-only, hash-chained record of every governed action."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void verify()} disabled={!isAdmin || verifying}>
              {verifying ? "Verifying…" : "Verify chain"}
            </Button>
            <Button
              variant="outline"
              disabled={!isAdmin}
              onClick={() => window.open(`${API_V1}/admin/audit/export`, "_blank")}
            >
              Export CSV
            </Button>
          </div>
        }
      />
      {!isAdmin ? (
        <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
          Chain verification and export require the admin role.
        </p>
      ) : null}

      {verifyResult ? (
        <div
          role="status"
          className={`mb-4 rounded-lg border p-3 text-sm ${
            verifyResult.ok
              ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "border-destructive/40 bg-destructive/10"
          }`}
        >
          {verifyResult.message} (checked {verifyResult.checked})
          {!verifyResult.ok && verifyResult.first_bad_seq !== null ? (
            <span> — first bad sequence: {verifyResult.first_bad_seq}</span>
          ) : null}
        </div>
      ) : null}

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <div className="grid gap-1.5">
          <Label htmlFor="a-event">Event type</Label>
          <Input
            id="a-event"
            placeholder="e.g. policy.created"
            value={filters.eventType}
            onChange={(e) => {
              setFilters({ ...filters, eventType: e.target.value });
              setOffset(0);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="a-resource">Resource type</Label>
          <Input
            id="a-resource"
            placeholder="e.g. policy"
            value={filters.resourceType}
            onChange={(e) => {
              setFilters({ ...filters, resourceType: e.target.value });
              setOffset(0);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="a-outcome">Outcome</Label>
          <Select
            id="a-outcome"
            value={filters.outcome}
            onChange={(e) => {
              setFilters({ ...filters, outcome: e.target.value });
              setOffset(0);
            }}
          >
            <option value="">All</option>
            <option value="success">success</option>
            <option value="denied">denied</option>
            <option value="error">error</option>
          </Select>
        </div>
      </div>

      {loading ? (
        <TableSkeleton rows={8} />
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No audit entries match." description="Actions appear here as soon as anything is changed." />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seq</TableHead>
                <TableHead>Time</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Hash</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-mono text-xs">{entry.seq}</TableCell>
                  <TableCell>{dateTime(entry.created_at)}</TableCell>
                  <TableCell className="font-mono text-xs">{entry.event_type}</TableCell>
                  <TableCell className="text-xs">{entry.actor_email ?? "—"}</TableCell>
                  <TableCell className="text-xs">
                    {entry.resource_type}
                    {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={entry.outcome} />
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => setSelected(entry.detail)}>
                      detail
                    </Button>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {entry.hash.slice(0, 8)}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {data.total} entries · showing {data.items.length}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset <= 0}
                onClick={() => setOffset(Math.max(0, offset - LIMIT))}
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
                onClick={() => setOffset(offset + LIMIT)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <Dialog open={selected !== null} onClose={() => setSelected(null)} title="Entry detail">
        <pre className="max-h-80 overflow-auto rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(selected, null, 2)}
        </pre>
      </Dialog>
    </div>
  );
}
