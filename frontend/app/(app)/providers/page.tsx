"use client";

// GET /admin/providers (developer+); create + update need admin+.
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner, errorText, requestIdOf } from "@/components/error-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch, ApiError } from "@/lib/api";
import type { ProviderIn, ProviderOut } from "@/lib/types";
import { canAdmin } from "@/lib/role";

const KINDS: ProviderIn["kind"][] = ["openai", "anthropic", "gemini", "ollama", "mock"];

export default function ProvidersPage() {
  const { me } = useAuth();
  const { toast } = useToast();
  const { data, error, loading, refetch } = useApi<ProviderOut[]>(
    `${API_V1}/admin/providers`,
  );

  const isAdmin = canAdmin(me?.role);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const [draft, setDraft] = useState({
    kind: "openai" as ProviderIn["kind"],
    name: "",
    base_url: "",
    api_key: "",
  });

  const create = async () => {
    setSaving(true);
    setFormError(null);
    try {
      const body: ProviderIn = {
        kind: draft.kind,
        name: draft.name,
        base_url: draft.base_url,
        secret_ref: "",
        enabled: true,
        api_key: draft.api_key || null,
      };
      await apiFetch<ProviderOut>(`${API_V1}/admin/providers`, {
        method: "POST",
        body,
      });
      toast({
        title: "Provider created.",
        description:
          "The API key is not stored by the backend — export it server-side under the returned secret_ref.",
      });
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

  const toggle = async (provider: ProviderOut, next: boolean) => {
    try {
      // PUT expects the full ProviderIn payload.
      const body: ProviderIn = {
        kind: provider.kind as ProviderIn["kind"],
        name: provider.name,
        base_url: provider.base_url,
        secret_ref: provider.secret_ref,
        enabled: next,
      };
      await apiFetch<ProviderOut>(`${API_V1}/admin/providers/${provider.id}`, {
        method: "PUT",
        body,
      });
      toast({ title: next ? "Provider enabled." : "Provider disabled." });
      refetch();
    } catch (err) {
      toast({
        title: "Update failed",
        description: errorText(err),
        variant: "destructive",
        requestId: requestIdOf(err),
      });
    }
  };

  return (
    <div>
      <PageHeader
        title="Providers"
        description="Upstream model providers. Secrets live server-side, never in the browser."
        actions={
          <Button onClick={() => setCreating(true)} disabled={!isAdmin}>
            Add provider
          </Button>
        }
      />
      {!isAdmin ? (
        <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
          Adding or changing providers requires the admin role.
        </p>
      ) : null}

      {loading ? (
        <TableSkeleton rows={4} />
      ) : error ? (
        <ErrorBanner error={error} onRetry={refetch} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No providers configured."
          description="Add one to route traffic beyond the built-in mock provider."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((provider) => {
            const isMock = provider.kind === "mock";
            return (
              <Card key={provider.id}>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{provider.name}</p>
                      <p className="font-mono text-xs text-muted-foreground">
                        {provider.kind} · {provider.base_url}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={provider.configured ? "success" : "warning"}>
                        {provider.configured ? "configured" : "secret missing"}
                      </Badge>
                      <Badge variant="outline">{provider.model_count} models</Badge>
                      {isMock ? <Badge variant="warning">simulated</Badge> : null}
                      <Switch
                        checked={provider.enabled}
                        disabled={!isAdmin}
                        onChange={(next) => void toggle(provider, next)}
                        label={`${provider.enabled ? "Disable" : "Enable"} ${provider.name}`}
                      />
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    secret_ref: <span className="font-mono">{provider.secret_ref || "—"}</span>
                  </p>
                  {isMock ? (
                    <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                      The mock provider returns simulated responses.
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {creating ? (
        <Dialog
          open
          onClose={() => setCreating(false)}
          title="Add provider"
          description="The API key is sent once so the backend can derive a secret_ref; it is never persisted in plaintext."
          footer={
            <>
              <Button onClick={() => void create()} disabled={saving || !draft.name.trim()}>
                {saving ? "Adding…" : "Add provider"}
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
            <Label htmlFor="p-kind">Kind</Label>
            <Select
              id="p-kind"
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value as ProviderIn["kind"] })}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="p-name">Name</Label>
            <Input
              id="p-name"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="p-url">Base URL</Label>
            <Input
              id="p-url"
              placeholder="https://api.openai.com/v1"
              value={draft.base_url}
              onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="p-key">API key (optional — used to derive secret_ref)</Label>
            <Input
              id="p-key"
              type="password"
              autoComplete="off"
              value={draft.api_key}
              onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
            />
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
