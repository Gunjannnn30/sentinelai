"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner, errorText, requestIdOf } from "@/components/error-banner";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch, ApiError } from "@/lib/api";
import type {
  PolicyCondition,
  PolicyField,
  PolicyIn,
  PolicyOut,
  PolicyPreviewOut,
} from "@/lib/types";
import { canAdmin, canWrite } from "@/lib/role";

const EMPTY_POLICY: PolicyIn = {
  name: "",
  description: "",
  enabled: true,
  severity: "medium",
  action: "block",
  scope: "organization",
  scope_role: null,
  project_id: null,
  conditions: [],
};

const FIELDS: PolicyField[] = [
  "prompt_injection_category",
  "pii_type",
  "prompt_contains",
  "model",
  "provider",
  "message_role",
  "project_id",
  "actor_role",
  "prompt_length_over",
  "response_contains",
];
const OPS = ["equals", "contains", "in", "gte", "matches"];

export default function PoliciesPage() {
  const { me } = useAuth();
  const { toast } = useToast();
  const { data, error, loading, refetch } = useApi<PolicyOut[]>(`${API_V1}/policies`);

  const canWritePolicies = canWrite(me?.role);
  const canDelete = canAdmin(me?.role);

  const [editing, setEditing] = useState<PolicyIn | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const [preview, setPreview] = useState<PolicyPreviewOut | null>(null);
  const [previewPrompt, setPreviewPrompt] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    setPreview(null);
  }, [editing]);

  const openCreate = () => {
    setEditingId(null);
    setEditing({ ...EMPTY_POLICY });
    setFormError(null);
  };

  const openEdit = (policy: PolicyOut) => {
    setEditingId(policy.id);
    setEditing({
      name: policy.name,
      description: policy.description,
      enabled: policy.enabled,
      severity: policy.severity,
      action: policy.action,
      scope: policy.scope,
      scope_role: policy.scope_role,
      project_id: policy.project_id,
      conditions: policy.conditions,
    });
    setFormError(null);
  };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    setFormError(null);
    try {
      if (editingId) {
        await apiFetch<PolicyOut>(`${API_V1}/policies/${editingId}`, {
          method: "PUT",
          body: editing,
        });
        toast({ title: "Policy updated." });
      } else {
        await apiFetch<PolicyOut>(`${API_V1}/policies`, {
          method: "POST",
          body: editing,
        });
        toast({ title: "Policy created." });
      }
      setEditing(null);
      refetch();
    } catch (err) {
      setFormError(err);
      if (err instanceof ApiError && err.status !== 422) {
        toast({ title: "Save failed", description: err.message, variant: "destructive", requestId: err.requestId });
      }
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    if (!editing) return;
    setPreviewing(true);
    setFormError(null);
    try {
      const out = await apiFetch<PolicyPreviewOut>(`${API_V1}/policies/preview`, {
        method: "POST",
        body: {
          policy: editing,
          prompt: previewPrompt,
          actor_role: me?.role ?? "viewer",
        },
      });
      setPreview(out);
    } catch (err) {
      setFormError(err);
    } finally {
      setPreviewing(false);
    }
  };

  const remove = async (id: string) => {
    setDeletingId(id);
    try {
      await apiFetch<void>(`${API_V1}/policies/${id}`, { method: "DELETE" });
      toast({ title: "Policy deleted." });
      refetch();
    } catch (err) {
      toast({
        title: "Delete failed",
        description: errorText(err),
        variant: "destructive",
        requestId: requestIdOf(err),
      });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Policies"
        description="Guardrail rules evaluated on every request, in order."
        actions={
          <Button onClick={openCreate} disabled={!canWritePolicies}>
            New policy
          </Button>
        }
      />
      {!canWritePolicies ? (
        <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
          Your role can view policies but not change them.
        </p>
      ) : null}

      {loading ? (
        <TableSkeleton rows={4} />
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No policies yet."
          description="Policies are evaluated top to bottom; the first matching action wins."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((policy) => (
            <Card key={policy.id}>
              <CardContent className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{policy.name}</span>
                    <StatusBadge value={policy.action} />
                    <Badge variant="secondary">{policy.severity}</Badge>
                    <Badge variant="outline">{policy.scope}</Badge>
                    {!policy.enabled ? <Badge variant="destructive">disabled</Badge> : null}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!canWritePolicies}
                      onClick={() => openEdit(policy)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={!canDelete || deletingId === policy.id}
                      onClick={() => void remove(policy.id)}
                    >
                      {deletingId === policy.id ? "Deleting…" : "Delete"}
                    </Button>
                  </div>
                </div>
                {policy.description ? (
                  <p className="mt-2 text-sm text-muted-foreground">{policy.description}</p>
                ) : null}
                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {policy.conditions.map((c, i) => (
                    <li key={i} className="font-mono">
                      {c.field} {c.op} {JSON.stringify(c.value)}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">
                  v{policy.version} · updated {new Date(policy.updated_at).toLocaleDateString()}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing ? (
        <Dialog
          open
          onClose={() => setEditing(null)}
          title={editingId ? "Edit policy" : "New policy"}
          description="Preview the draft against a sample prompt before saving."
          footer={
            <>
              {canWritePolicies ? (
                <Button onClick={() => void save()} disabled={saving || !editing.name.trim()}>
                  {saving ? "Saving…" : editingId ? "Save changes" : "Create policy"}
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </>
          }
        >
          {formError instanceof ApiError ? (
            <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
              <p className="font-medium text-destructive">{formError.message}</p>
              {formError.requestId ? (
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  request_id: {formError.requestId}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-2">
            <Label htmlFor="pol-name">Name</Label>
            <Input
              id="pol-name"
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pol-desc">Description</Label>
            <Textarea
              id="pol-desc"
              rows={2}
              value={editing.description}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="pol-action">Action</Label>
              <Select
                id="pol-action"
                value={editing.action}
                onChange={(e) =>
                  setEditing({ ...editing, action: e.target.value as PolicyIn["action"] })
                }
              >
                <option value="allow">allow</option>
                <option value="warn">warn</option>
                <option value="mask">mask</option>
                <option value="block">block</option>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pol-sev">Severity</Label>
              <Select
                id="pol-sev"
                value={editing.severity}
                onChange={(e) =>
                  setEditing({ ...editing, severity: e.target.value as PolicyIn["severity"] })
                }
              >
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="critical">critical</option>
              </Select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={editing.enabled}
              onChange={(next) => setEditing({ ...editing, enabled: next })}
              label="Policy enabled"
            />
            <span className="text-sm text-muted-foreground">Enabled</span>
          </div>

          <div className="grid gap-2">
            <Label>Conditions</Label>
            {editing.conditions.map((cond, i) => (
              <div key={i} className="grid grid-cols-[1fr_90px_1fr_auto] items-center gap-2">
                <Select
                  aria-label={`Condition ${i + 1} field`}
                  value={cond.field}
                  onChange={(e) =>
                    updateCondition(editing, setEditing, i, {
                      field: e.target.value as PolicyField,
                    })
                  }
                >
                  {FIELDS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label={`Condition ${i + 1} operator`}
                  value={cond.op}
                  onChange={(e) =>
                    updateCondition(editing, setEditing, i, {
                      op: e.target.value as PolicyCondition["op"],
                    })
                  }
                >
                  {OPS.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label={`Condition ${i + 1} value`}
                  value={String(cond.value ?? "")}
                  onChange={(e) =>
                    updateCondition(editing, setEditing, i, { value: e.target.value })
                  }
                />
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove condition ${i + 1}`}
                  onClick={() =>
                    setEditing({
                      ...editing,
                      conditions: editing.conditions.filter((_, j) => j !== i),
                    })
                  }
                >
                  ✕
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              className="justify-self-start"
              onClick={() =>
                setEditing({
                  ...editing,
                  conditions: [
                    ...editing.conditions,
                    { field: "prompt_contains", op: "contains", value: "" },
                  ],
                })
              }
            >
              Add condition
            </Button>
          </div>

          <div className="grid gap-2 border-t pt-4">
            <Label htmlFor="pol-preview">Preview against a sample prompt</Label>
            <Textarea
              id="pol-preview"
              rows={3}
              value={previewPrompt}
              onChange={(e) => setPreviewPrompt(e.target.value)}
              placeholder="Paste a sample user prompt…"
            />
            <Button
              variant="secondary"
              size="sm"
              className="justify-self-start"
              onClick={() => void runPreview()}
              disabled={previewing || !canWritePolicies}
            >
              {previewing ? "Previewing…" : "Run preview"}
            </Button>
            {preview ? (
              <div className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {preview.decision.matched ? "Would match" : "No match"}
                  </span>
                  <StatusBadge value={preview.decision.action} />
                  <Badge variant="secondary">{preview.decision.severity}</Badge>
                </div>
                {preview.decision.explanation ? (
                  <p className="mt-1 text-muted-foreground">{preview.decision.explanation}</p>
                ) : null}
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
                  {JSON.stringify(
                    { injection: preview.injection, pii: preview.pii },
                    null,
                    2,
                  )}
                </pre>
              </div>
            ) : null}
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}

function updateCondition(
  policy: PolicyIn,
  set: (p: PolicyIn) => void,
  index: number,
  patch: Partial<PolicyCondition>,
) {
  const conditions = policy.conditions.map((c, i) =>
    i === index ? { ...c, ...patch } : c,
  );
  set({ ...policy, conditions });
}
