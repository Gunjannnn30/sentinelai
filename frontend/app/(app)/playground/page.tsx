"use client";

import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner } from "@/components/error-banner";
import { ChatResult } from "@/components/playground/chat-result";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/ui/empty-state";
import { useApi } from "@/hooks/use-api";
import { useToast } from "@/components/ui/toast";
import { API_V1, apiFetch, ApiError } from "@/lib/api";
import type { ChatCompletionIn, ChatCompletionOut, ModelOut } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { canWrite } from "@/lib/role";
import { money } from "@/lib/format";

export default function PlaygroundPage() {
  const { me } = useAuth();
  const { data: models } = useApi<ModelOut[]>(`${API_V1}/models`);
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [system, setSystem] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<ChatCompletionOut | null>(null);
  const { toast } = useToast();

  const allowlisted = (models ?? []).filter((m) => m.enabled);
  const readOnly = !canWrite(me?.role);

  const send = async () => {
    if (!prompt.trim()) return;
    setSending(true);
    setError(null);
    try {
      const messages: ChatCompletionIn["messages"] = [];
      if (system.trim()) messages.push({ role: "system", content: system });
      messages.push({ role: "user", content: prompt });
      const body: ChatCompletionIn = { messages, dry_run: dryRun };
      if (model) body.model = model;
      const out = await apiFetch<ChatCompletionOut>(`${API_V1}/chat/completions`, {
        method: "POST",
        body,
      });
      setResult(out);
      if (out.status !== "success") {
        toast({
          title: out.status === "blocked" ? "Request blocked" : "Gateway error",
          description:
            out.error?.blocked_reason ??
            out.error?.message ??
            `status: ${out.status}`,
          variant: "destructive",
          requestId: out.request_id,
        });
      }
    } catch (err) {
      setError(err);
      if (err instanceof ApiError) {
        toast({
          title: "Request failed",
          description: err.message,
          variant: "destructive",
          requestId: err.requestId,
        });
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Playground"
        description="Send one message through the full guardrail pipeline."
      />
      {readOnly ? (
        <p className="mb-4 rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
          Your role can view results but not send new requests.
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Request</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="pg-model">Model (optional — router decides when omitted)</Label>
              <Select id="pg-model" value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="">Auto-route</option>
                {allowlisted.map((m) => (
                  <option key={m.id} value={m.model_key}>
                    {m.display_name} ({m.provider_kind})
                  </option>
                ))}
              </Select>
              {allowlisted.some((m) => m.is_demo_data) ? (
                <p className="text-xs text-muted-foreground">
                  Models marked as demo return simulated responses.
                </p>
              ) : null}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pg-system">System message (optional)</Label>
              <Textarea
                id="pg-system"
                value={system}
                onChange={(e) => setSystem(e.target.value)}
                rows={2}
                placeholder="You are a helpful assistant."
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pg-prompt">User prompt</Label>
              <Textarea
                id="pg-prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="Ask the model something…"
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Switch checked={dryRun} onChange={setDryRun} label="Dry run" />
                <span className="text-sm text-muted-foreground">
                  Dry run — guardrails only, no provider call
                </span>
              </div>
              <Button onClick={() => void send()} disabled={sending || readOnly || !prompt.trim()}>
                {sending ? "Sending…" : dryRun ? "Run guardrails" : "Send"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {error ? <ErrorBanner error={error} onRetry={() => void send()} /> : null}
          {result ? (
            <ChatResult result={result} />
          ) : !error ? (
            <EmptyState
              title="No response yet."
              description="Results appear here after you send a message. Errors and blocks are never hidden."
            />
          ) : null}
        </div>
      </div>

      {allowlisted.length > 0 ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Allowlisted models</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {allowlisted.map((m) => (
                <li key={m.id} className="rounded-md border p-3">
                  <p className="font-medium">{m.display_name}</p>
                  <p className="text-xs text-muted-foreground">{m.provider_kind}</p>
                  <p className="mt-1 text-xs">
                    in: {money(m.input_cost_per_1m)} / 1M · out: {money(m.output_cost_per_1m)} / 1M
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
