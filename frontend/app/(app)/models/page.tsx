"use client";

// GET /admin/models (developer+), POST /admin/models (admin+). There is NO
// update endpoint in the backend, so enabled state is read-only here — it can
// only be set at creation time.
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner } from "@/components/error-banner";
import { DemoBadge } from "@/components/demo-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch, ApiError } from "@/lib/api";
import type { AdminModelRow, ProviderOut } from "@/lib/types";
import { canAdmin } from "@/lib/role";
import { money } from "@/lib/format";

export default function ModelsPage() {
  const { me } = useAuth();
  const { toast } = useToast();
  const { data, error, loading, refetch } = useApi<AdminModelRow[]>(
    `${API_V1}/admin/models`,
  );
  const { data: providers } = useApi<ProviderOut[]>(`${API_V1}/admin/providers`);

  const isAdmin = canAdmin(me?.role);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const [draft, setDraft] = useState({
    provider_id: "",
    model_key: "",
    display_name: "",
    input_cost_per_1m: "",
    output_cost_per_1m: "",
    priority: "100",
  });

  const create = async () => {
    setSaving(true);
    setFormError(null);
    try {
      await apiFetch(`${API_V1}/admin/models`, {
        method: "POST",
        body: {
          provider_id: draft.provider_id,
          model_key: draft.model_key,
          display_name: draft.display_name || draft.model_key,
          capabilities: ["chat"],
          input_cost_per_1m: draft.input_cost_per_1m ? Number(draft.input_cost_per_1m) : null,
          output_cost_per_1m: draft.output_cost_per_1m ? Number(draft.output_cost_per_1m) : null,
          pricing_source: draft.input_cost_per_1m ? "manual" : null,
          priority: Number(draft.priority) || 100,
          latency_class: "medium",
          enabled: true,
        },
      });
      toast({ title: "Model added to the allowlist." });
      setCreating(false);
      refetch();
    } catch (err) {
      setFormError(err);
      if (err instanceof ApiError && err.status !== 422) {
        toast({ title: "Create failed", description: err.message, variant: "destructive", requestId: err.requestId });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Models"
        description="Allowlisted models and their routing priority."
        actions={
          <Button onClick={() => setCreating(true)} disabled={!isAdmin}>
            Add model
          </Button>
        }
      />
      <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
        The backend exposes only create for models — there is no update endpoint,
        so the enabled flag shown here is read-only.
      </p>
      {!isAdmin ? (
        <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
          Adding models requires the admin role.
        </p>
      ) : null}

      {loading ? (
        <TableSkeleton rows={5} />
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No models configured."
          description="Add a provider first, then register models on it."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((model) => (
            <Card key={model.id}>
              <CardContent className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium">{model.display_name}</p>
                    <p className="font-mono text-xs text-muted-foreground">{model.model_key}</p>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {model.enabled ? (
                      <Badge variant="success">enabled</Badge>
                    ) : (
                      <Badge variant="destructive">disabled</Badge>
                    )}
                    <Badge variant="outline">{model.provider}</Badge>
                    <DemoBadge isDemo={model.is_demo_data} />
                  </div>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <div>
                    <dt>Priority</dt>
                    <dd className="font-medium text-foreground">{model.priority}</dd>
                  </div>
                  <div>
                    <dt>Latency class</dt>
                    <dd className="font-medium text-foreground">{model.latency_class}</dd>
                  </div>
                  <div>
                    <dt>Context window</dt>
                    <dd className="font-medium text-foreground">
                      {model.context_window?.toLocaleString() ?? "Unavailable"}
                    </dd>
                  </div>
                  <div>
                    <dt>Input / 1M</dt>
                    <dd className="font-medium text-foreground">{money(model.input_cost_per_1m)}</dd>
                  </div>
                  <div>
                    <dt>Output / 1M</dt>
                    <dd className="font-medium text-foreground">{money(model.output_cost_per_1m)}</dd>
                  </div>
                  <div>
                    <dt>Pricing source</dt>
                    <dd className="font-medium text-foreground">{model.pricing_source ?? "Unavailable"}</dd>
                  </div>
                </dl>
                {model.capabilities.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {model.capabilities.map((cap) => (
                      <Badge key={cap} variant="secondary">
                        {cap}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {creating ? (
        <Dialog
          open
          onClose={() => setCreating(false)}
          title="Add model"
          description="Registers a model on an existing provider. Enabled at creation; the API has no update route."
          footer={
            <>
              <Button onClick={() => void create()} disabled={saving || !draft.provider_id || !draft.model_key}>
                {saving ? "Adding…" : "Add model"}
              </Button>
              <Button variant="outline" onClick={() => setCreating(false)}>
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
            <Label htmlFor="m-provider">Provider</Label>
            <Select
              id="m-provider"
              value={draft.provider_id}
              onChange={(e) => setDraft({ ...draft, provider_id: e.target.value })}
            >
              <option value="">Select a provider…</option>
              {(providers ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.kind})
                </option>
              ))}
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-key">Model key</Label>
            <Input
              id="m-key"
              placeholder="gpt-4o-mini"
              value={draft.model_key}
              onChange={(e) => setDraft({ ...draft, model_key: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-name">Display name</Label>
            <Input
              id="m-name"
              value={draft.display_name}
              onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="m-in">Input $ / 1M tokens</Label>
              <Input
                id="m-in"
                inputMode="decimal"
                value={draft.input_cost_per_1m}
                onChange={(e) => setDraft({ ...draft, input_cost_per_1m: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="m-out">Output $ / 1M tokens</Label>
              <Input
                id="m-out"
                inputMode="decimal"
                value={draft.output_cost_per_1m}
                onChange={(e) => setDraft({ ...draft, output_cost_per_1m: e.target.value })}
              />
            </div>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
