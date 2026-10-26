"use client";

// Datasets/cases/runs are readable by every role; creating a dataset or
// starting a run needs developer or more (backend evals_api.py).
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ErrorBanner, errorText, requestIdOf } from "@/components/error-banner";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { TabPanel, Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/hooks/use-auth";
import { API_V1, apiFetch } from "@/lib/api";
import type {
  EvalDatasetOut,
  EvalResultOut,
  EvalRunDetailOut,
  EvalRunOut,
  EvalRunSummaryModel,
  ModelOut,
} from "@/lib/types";
import { canWrite } from "@/lib/role";
import { dateTime, money, ms, num, pct } from "@/lib/format";

export default function EvaluationsPage() {
  const { me } = useAuth();
  const { toast } = useToast();
  const [tab, setTab] = useState("datasets");

  const canRun = canWrite(me?.role);

  const datasets = useApi<EvalDatasetOut[]>(`${API_V1}/evals/datasets`);
  const runs = useApi<EvalRunOut[]>(`${API_V1}/evals/runs`);
  const models = useApi<ModelOut[]>(`${API_V1}/models`);

  const [creatingDataset, setCreatingDataset] = useState(false);
  const [datasetName, setDatasetName] = useState("");
  const [datasetDesc, setDatasetDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [runDraft, setRunDraft] = useState({ name: "", dataset_id: "", model_keys: "" });
  const [openRunId, setOpenRunId] = useState<string | null>(null);

  const createDataset = async () => {
    setSaving(true);
    try {
      await apiFetch(`${API_V1}/evals/datasets`, {
        method: "POST",
        body: { name: datasetName, description: datasetDesc },
      });
      toast({ title: "Dataset created." });
      setCreatingDataset(false);
      setDatasetName("");
      setDatasetDesc("");
      datasets.refetch();
    } catch (err) {
      toast({ title: "Create failed", description: errorText(err), variant: "destructive", requestId: requestIdOf(err) });
    } finally {
      setSaving(false);
    }
  };

  const startRun = async () => {
    setSaving(true);
    try {
      const model_keys = runDraft.model_keys
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean);
      const name =
        runDraft.name.trim().length >= 2
          ? runDraft.name.trim()
          : `Run ${new Date().toISOString().slice(0, 16)}`;
      await apiFetch<EvalRunOut>(`${API_V1}/evals/runs`, {
        method: "POST",
        body: {
          name,
          dataset_id: runDraft.dataset_id,
          model_keys,
        },
      });
      toast({ title: "Run started." });
      setRunDraft({ name: "", dataset_id: "", model_keys: "" });
      runs.refetch();
      setTab("runs");
    } catch (err) {
      toast({ title: "Run failed to start", description: errorText(err), variant: "destructive", requestId: requestIdOf(err) });
    } finally {
      setSaving(false);
    }
  };

  const allowlisted = (models.data ?? []).filter((m) => m.enabled);

  return (
    <div>
      <PageHeader
        title="Evaluations"
        description="Score models against labelled datasets and compare runs to a baseline."
      />
      <Tabs
        tabs={[
          { value: "datasets", label: "Datasets" },
          { value: "runs", label: "Runs" },
        ]}
        value={tab}
        onChange={setTab}
      />

      <TabPanel value="datasets" active={tab}>
        <div className="mb-4 flex justify-end">
          <Button onClick={() => setCreatingDataset(true)} disabled={!canRun}>
            New dataset
          </Button>
        </div>
        {datasets.loading ? (
          <TableSkeleton rows={3} />
        ) : datasets.error ? (
          <ErrorBanner error={datasets.error} onRetry={datasets.refetch} />
        ) : !datasets.data || datasets.data.length === 0 ? (
          <EmptyState
            title="No datasets yet."
            description="A dataset holds prompt/expected pairs used to score models."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {datasets.data.map((ds) => (
              <Card key={ds.id}>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">{ds.name}</p>
                    <div className="flex gap-1">
                      <Badge variant="outline">{num(ds.case_count)} cases</Badge>
                      {ds.is_synthetic ? <Badge variant="warning">synthetic</Badge> : null}
                    </div>
                  </div>
                  {ds.description ? (
                    <p className="mt-1 text-sm text-muted-foreground">{ds.description}</p>
                  ) : null}
                  <p className="mt-2 text-xs text-muted-foreground">{dateTime(ds.created_at)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </TabPanel>

      <TabPanel value="runs" active={tab}>
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">Start a run</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="grid gap-1.5">
              <Label htmlFor="run-name">Name</Label>
              <Input
                id="run-name"
                value={runDraft.name}
                onChange={(e) => setRunDraft({ ...runDraft, name: e.target.value })}
                placeholder="Optional"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="run-dataset">Dataset</Label>
              <Select
                id="run-dataset"
                value={runDraft.dataset_id}
                onChange={(e) => setRunDraft({ ...runDraft, dataset_id: e.target.value })}
              >
                <option value="">Select…</option>
                {(datasets.data ?? []).map((ds) => (
                  <option key={ds.id} value={ds.id}>
                    {ds.name} ({ds.case_count})
                  </option>
                ))}
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="run-models">Models (comma separated keys)</Label>
              <Input
                id="run-models"
                value={runDraft.model_keys}
                onChange={(e) => setRunDraft({ ...runDraft, model_keys: e.target.value })}
                placeholder={allowlisted[0]?.model_key ?? "gpt-4o-mini"}
              />
            </div>
            <div className="md:col-span-3">
              <Button
                onClick={() => void startRun()}
                disabled={saving || !canRun || !runDraft.dataset_id || !runDraft.model_keys.trim()}
              >
                {saving ? "Starting…" : "Start run"}
              </Button>
              {!canRun ? (
                <p className="mt-2 text-sm text-muted-foreground">
                  Starting runs requires the developer role.
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {runs.loading ? (
          <TableSkeleton rows={3} />
        ) : runs.error ? (
          <ErrorBanner error={runs.error} onRetry={runs.refetch} />
        ) : !runs.data || runs.data.length === 0 ? (
          <EmptyState title="No runs yet." description="Start one from a dataset above." />
        ) : (
          <div className="space-y-3">
            {runs.data.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                expanded={openRunId === run.id}
                onToggle={() => setOpenRunId(openRunId === run.id ? null : run.id)}
              />
            ))}
          </div>
        )}
      </TabPanel>

      <Dialog
        open={creatingDataset}
        onClose={() => setCreatingDataset(false)}
        title="New dataset"
        description="Cases are added through the API; the UI lists them read-only."
        footer={
          <>
            <Button onClick={() => void createDataset()} disabled={saving || !datasetName.trim()}>
              {saving ? "Creating…" : "Create"}
            </Button>
            <Button variant="outline" onClick={() => setCreatingDataset(false)}>
              Cancel
            </Button>
          </>
        }
      >
        <div className="grid gap-2">
          <Label htmlFor="ds-name">Name</Label>
          <Input id="ds-name" value={datasetName} onChange={(e) => setDatasetName(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="ds-desc">Description</Label>
          <Textarea id="ds-desc" rows={2} value={datasetDesc} onChange={(e) => setDatasetDesc(e.target.value)} />
        </div>
      </Dialog>
    </div>
  );
}

function RunCard({
  run,
  expanded,
  onToggle,
}: {
  run: EvalRunOut;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detail = useApi<EvalRunDetailOut>(
    expanded ? `${API_V1}/evals/runs/${run.id}` : null,
  );
  const summary = run.summary ?? {};
  const models = summary.models ?? {};
  const regression = summary.regression;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{run.name}</span>
            <StatusBadge value={run.status} />
            {summary.judge_enabled ? <Badge variant="secondary">judge enabled</Badge> : null}
            {run.baseline_run_id ? <Badge variant="outline">has baseline</Badge> : null}
          </div>
          <Button variant="outline" size="sm" onClick={onToggle}>
            {expanded ? "Hide details" : "Show details"}
          </Button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {run.model_keys.join(", ")} · started {run.started_at ? dateTime(run.started_at) : "—"}
          {run.finished_at ? ` · finished ${dateTime(run.finished_at)}` : ""}
        </p>

        {Object.keys(models).length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-2 py-1">Model</th>
                  <th className="px-2 py-1">Cases</th>
                  <th className="px-2 py-1">Avg score</th>
                  <th className="px-2 py-1">Completion</th>
                  <th className="px-2 py-1">Errors</th>
                  <th className="px-2 py-1">Latency</th>
                  <th className="px-2 py-1">Cost</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(models).map(([key, m]: [string, EvalRunSummaryModel]) => (
                  <tr key={key} className="border-b last:border-0">
                    <td className="px-2 py-1 font-medium">{key}</td>
                    <td className="px-2 py-1">{num(m.cases)}</td>
                    <td className="px-2 py-1">{m.avg_score === null ? "—" : m.avg_score.toFixed(3)}</td>
                    <td className="px-2 py-1">{pct(m.completion_rate)}</td>
                    <td className="px-2 py-1">{num(m.errors)}</td>
                    <td className="px-2 py-1">{ms(m.avg_latency_ms)}</td>
                    <td className="px-2 py-1">{m.cost_available ? money(m.total_cost_usd) : "Unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {summary.scoring_note ? (
          <p className="mt-2 text-xs text-muted-foreground">{summary.scoring_note}</p>
        ) : null}

        {regression ? (
          <div className="mt-2 rounded-md border p-2 text-xs">
            <p className="font-medium">
              Regression vs baseline: {regression.available ? "available" : "unavailable"}
            </p>
            {regression.note ? (
              <p className="text-muted-foreground">{regression.note}</p>
            ) : null}
            {regression.models
              ? Object.entries(regression.models).map(([key, r]) => (
                  <p key={key} className="text-muted-foreground">
                    {key}: {r.delta === null ? "n/a" : r.delta.toFixed(3)}
                    {r.regressed ? " (regressed)" : ""} {r.note ? `— ${r.note}` : ""}
                  </p>
                ))
              : null}
          </div>
        ) : null}

        {expanded ? (
          detail.loading ? (
            <p className="mt-3 text-sm text-muted-foreground">Loading results…</p>
          ) : detail.error ? (
            <ErrorBanner error={detail.error} onRetry={detail.refetch} className="mt-3" />
          ) : detail.data ? (
            <ResultList results={detail.data.results} />
          ) : null
        ) : null}
      </CardContent>
    </Card>
  );
}

function ResultList({ results }: { results: EvalResultOut[] }) {
  if (results.length === 0) {
    return <p className="mt-3 text-sm text-muted-foreground">No results recorded.</p>;
  }
  return (
    <div className="mt-3 space-y-2">
      <h4 className="text-sm font-medium">Results ({results.length})</h4>
      {results.slice(0, 25).map((r) => (
        <div key={r.id} className="rounded-md border p-2 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{r.model_key}</span>
            <StatusBadge value={r.status} />
            <span className="text-muted-foreground">{ms(r.latency_ms)}</span>
            {Object.entries(r.metrics ?? {}).map(([name, m]) => (
              <span key={name} className="text-muted-foreground">
                {name}: {m.score === null ? "—" : m.score.toFixed(3)}
              </span>
            ))}
          </div>
          {r.output ? (
            <p className="mt-1 line-clamp-3 text-muted-foreground">{r.output}</p>
          ) : null}
          {r.error_category ? (
            <p className="mt-1 text-destructive">{r.error_category}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
