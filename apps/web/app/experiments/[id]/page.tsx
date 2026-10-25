"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  ExternalLink,
  Gauge,
  GitCompareArrows,
  Play,
  ShieldCheck,
  Square,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button, Card, Label, PageLoader, Spinner } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { type Experiment, type ExperimentRunPage } from "@/lib/experiments";
import {
  type MetricComparison,
  type QualityGate,
  type QualityGateResult,
} from "@/lib/quality-gates";

function formatMetric(value: number | string | undefined, suffix = "") {
  if (value == null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return `${numeric.toLocaleString(undefined, { maximumFractionDigits: 3 })}${suffix}`;
}

function statusClass(status: string) {
  if (status === "COMPLETED") return "text-[var(--success)]";
  if (status === "RUNNING" || status === "EVALUATING")
    return "text-[var(--info)]";
  if (status === "FAILED") return "text-[var(--danger)]";
  if (status === "CANCELLED") return "text-[var(--warning)]";
  return "text-[var(--muted)]";
}

function JsonValue({ value }: { value: unknown }) {
  return (
    <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-[var(--code)] p-3 text-xs leading-5 text-[var(--code-text)]">
      {value == null ? "—" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function ExperimentDetail() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project_id") ?? "";
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [page, setPage] = useState(1);
  const [gateId, setGateId] = useState("");

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setReady(true));
  }, [clear, router, token]);

  const experiment = useQuery({
    queryKey: ["experiment", projectId, params.id],
    queryFn: () =>
      apiFetch<Experiment>(
        `/api/v1/projects/${projectId}/experiments/${params.id}`,
      ),
    enabled: ready && Boolean(projectId),
    refetchInterval: (query) =>
      query.state.data?.status === "RUNNING" ? 2_000 : false,
  });
  const runs = useQuery({
    queryKey: ["experiment-runs", projectId, params.id, page],
    queryFn: () =>
      apiFetch<ExperimentRunPage>(
        `/api/v1/projects/${projectId}/experiments/${params.id}/runs?page=${page}&page_size=25`,
      ),
    enabled: ready && Boolean(projectId),
    refetchInterval: experiment.data?.status === "RUNNING" ? 2_000 : false,
  });
  const comparison = useQuery({
    queryKey: ["experiment-comparison", projectId, params.id],
    queryFn: () =>
      apiFetch<MetricComparison[]>(
        `/api/v1/projects/${projectId}/experiments/${params.id}/comparison`,
      ),
    enabled:
      ready && Boolean(projectId) && experiment.data?.status === "COMPLETED",
    retry: false,
  });
  const gates = useQuery({
    queryKey: ["quality-gates", projectId],
    queryFn: () =>
      apiFetch<QualityGate[]>(`/api/v1/projects/${projectId}/quality-gates`),
    enabled: ready && Boolean(projectId),
  });
  const gateResults = useQuery({
    queryKey: ["quality-gate-results", projectId, params.id],
    queryFn: () =>
      apiFetch<QualityGateResult[]>(
        `/api/v1/projects/${projectId}/experiments/${params.id}/quality-gate-results`,
      ),
    enabled: ready && Boolean(projectId),
  });
  const start = useMutation({
    mutationFn: () =>
      apiFetch<Experiment>(
        `/api/v1/projects/${projectId}/experiments/${params.id}/start`,
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["experiment", projectId, params.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["experiment-runs", projectId, params.id],
      });
    },
  });
  const cancel = useMutation({
    mutationFn: () =>
      apiFetch<Experiment>(
        `/api/v1/projects/${projectId}/experiments/${params.id}/cancel`,
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["experiment", projectId, params.id],
      });
      queryClient.invalidateQueries({
        queryKey: ["experiment-runs", projectId, params.id],
      });
    },
  });
  const setBaseline = useMutation({
    mutationFn: () =>
      apiFetch(
        `/api/v1/projects/${projectId}/experiments/${params.id}/baseline`,
        {
          method: "POST",
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["experiment-comparison", projectId],
      });
    },
  });
  const activeGateId = gateId || gates.data?.[0]?.id || "";
  const evaluateGate = useMutation({
    mutationFn: () =>
      apiFetch<QualityGateResult>(
        `/api/v1/projects/${projectId}/quality-gates/${activeGateId}/evaluate`,
        {
          method: "POST",
          body: JSON.stringify({ candidate_experiment_id: params.id }),
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["quality-gate-results", projectId, params.id],
      });
    },
  });

  if (!projectId)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--danger)]">
        Open this experiment from its project experiment list.
      </div>
    );
  if (!ready || experiment.isLoading)
    return <PageLoader label="Loading experiment" />;
  if (!experiment.data || experiment.error)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--danger)]">
        {experiment.error?.message ?? "Experiment not found"}
      </div>
    );

  const data = experiment.data;
  const metrics = data.metrics;
  const progress = data.total_cases
    ? (data.completed_cases / data.total_cases) * 100
    : 0;
  const metricCards = [
    {
      label: "Pass rate",
      value: formatMetric(Number(metrics.pass_rate ?? 0) * 100, "%"),
      icon: Gauge,
    },
    {
      label: "Passed",
      value: `${data.passed_cases}/${data.total_cases}`,
      icon: CheckCircle2,
    },
    {
      label: "Failed",
      value: data.failed_cases.toString(),
      icon: XCircle,
    },
    {
      label: "P95 latency",
      value: formatMetric(metrics.p95_latency_ms, " ms"),
      icon: Clock3,
    },
    {
      label: "Total cost",
      value: `$${Number(metrics.total_cost ?? 0).toFixed(6)}`,
      icon: CircleDollarSign,
    },
  ];

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link
              href="/experiments"
              className="mb-3 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
            >
              <ArrowLeft size={15} /> Experiments
            </Link>
            <p className="text-sm font-medium text-[var(--muted)]">
              {data.dataset_name} / version {data.dataset_version}
            </p>
            <h1 className="mt-2 text-3xl font-semibold">{data.name}</h1>
            <p className={`mt-2 font-mono text-xs ${statusClass(data.status)}`}>
              {data.status}
            </p>
          </div>
          <div className="flex gap-2">
            {data.status === "PENDING" && (
              <Button
                onClick={() => start.mutate()}
                disabled={start.isPending}
                loading={start.isPending}
              >
                <Play size={15} className="mr-2" /> Start
              </Button>
            )}
            {data.status === "RUNNING" && (
              <Button
                variant="danger"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
                loading={cancel.isPending}
              >
                <Square size={14} className="mr-2" /> Cancel
              </Button>
            )}
            {data.status === "COMPLETED" && (
              <Button
                variant="outline"
                onClick={() => setBaseline.mutate()}
                disabled={setBaseline.isPending}
                loading={setBaseline.isPending}
              >
                <GitCompareArrows size={15} className="mr-2" /> Set as baseline
              </Button>
            )}
          </div>
        </div>

        <Card className="p-5">
          <div className="flex items-center justify-between text-xs text-[var(--muted)]">
            <span>
              {data.completed_cases} of {data.total_cases} cases terminal
            </span>
            <span>{progress.toFixed(0)}%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--surface-muted)]">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {metricCards.map((metric) => (
            <Card key={metric.label} className="p-4">
              <div className="flex items-center justify-between text-[var(--muted)]">
                <Label className="mb-0">{metric.label}</Label>
                <metric.icon size={16} />
              </div>
              <p className="mt-3 text-xl font-semibold">{metric.value}</p>
            </Card>
          ))}
        </div>

        {(metrics.average_correctness != null ||
          metrics.hallucination_rate != null ||
          metrics.tool_accuracy != null) && (
          <Card className="grid gap-4 p-5 sm:grid-cols-3">
            {metrics.average_correctness != null && (
              <div>
                <Label>Average correctness</Label>
                <p className="text-xl font-semibold">
                  {formatMetric(Number(metrics.average_correctness) * 100, "%")}
                </p>
              </div>
            )}
            {metrics.hallucination_rate != null && (
              <div>
                <Label>Hallucination rate</Label>
                <p className="text-xl font-semibold">
                  {formatMetric(Number(metrics.hallucination_rate) * 100, "%")}
                </p>
              </div>
            )}
            {metrics.tool_accuracy != null && (
              <div>
                <Label>Tool accuracy</Label>
                <p className="text-xl font-semibold">
                  {formatMetric(Number(metrics.tool_accuracy) * 100, "%")}
                </p>
              </div>
            )}
          </Card>
        )}

        {data.status === "COMPLETED" && (
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <Card className="overflow-hidden">
              <div className="border-b border-[var(--border)] p-5">
                <h2 className="font-semibold">Baseline comparison</h2>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Deltas use the baseline selected for this dataset lineage.
                </p>
              </div>
              {comparison.data?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                      <tr>
                        <th className="px-5 py-3">Metric</th>
                        <th className="px-5 py-3">Baseline</th>
                        <th className="px-5 py-3">Candidate</th>
                        <th className="px-5 py-3">Delta</th>
                        <th className="px-5 py-3">Result</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {comparison.data.map((item) => (
                        <tr key={item.metric}>
                          <td className="px-5 py-3 font-mono text-xs">
                            {item.metric}
                          </td>
                          <td className="px-5 py-3">
                            {formatMetric(item.baseline)}
                          </td>
                          <td className="px-5 py-3">
                            {formatMetric(item.candidate)}
                          </td>
                          <td className="px-5 py-3">
                            {formatMetric(item.absolute_delta)}
                            {item.percentage_delta != null && (
                              <span className="ml-1 text-xs text-[var(--muted)]">
                                (
                                {formatMetric(item.percentage_delta * 100, "%")}
                                )
                              </span>
                            )}
                          </td>
                          <td
                            className={`px-5 py-3 text-xs ${
                              item.classification === "REGRESSION"
                                ? "text-[var(--danger)]"
                                : item.classification === "IMPROVEMENT"
                                  ? "text-[var(--success)]"
                                  : "text-[var(--muted)]"
                            }`}
                          >
                            {item.classification}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-5 text-sm text-[var(--muted)]">
                  {comparison.isLoading ? (
                    <span className="flex items-center gap-2">
                      <Spinner size="sm" /> Loading comparison…
                    </span>
                  ) : (
                    "No comparison is available. Select a different completed experiment as the dataset baseline."
                  )}
                </p>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2">
                <ShieldCheck size={17} className="text-[var(--accent)]" />
                <h2 className="font-semibold">Release gate</h2>
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                Evaluate this candidate with a stored policy. Results and rule
                snapshots are retained for CI and audit history.
              </p>
              <div className="mt-4">
                <Label>Quality gate</Label>
                <select
                  className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
                  value={activeGateId}
                  onChange={(event) => setGateId(event.target.value)}
                >
                  {gates.data?.map((gate) => (
                    <option key={gate.id} value={gate.id}>
                      {gate.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  onClick={() => evaluateGate.mutate()}
                  disabled={
                    !activeGateId || !comparison.data || evaluateGate.isPending
                  }
                  loading={evaluateGate.isPending}
                >
                  Run quality gate
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/quality-gates">Manage gates</Link>
                </Button>
              </div>
              {(evaluateGate.error || setBaseline.error) && (
                <p className="mt-3 text-sm text-[var(--danger)]">
                  {evaluateGate.error?.message ?? setBaseline.error?.message}
                </p>
              )}
              <div className="mt-5 space-y-3">
                {gateResults.data?.map((result) => (
                  <div
                    key={result.id}
                    className="rounded-md border border-[var(--border)] p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`font-mono text-xs ${
                          result.status === "FAILED"
                            ? "text-[var(--danger)]"
                            : result.status === "PASSED_WITH_WARNINGS"
                              ? "text-[var(--warning)]"
                              : "text-[var(--success)]"
                        }`}
                      >
                        {result.status}
                      </span>
                      <span className="text-[10px] text-[var(--muted)]">
                        {new Date(result.evaluated_at).toLocaleString()}
                      </span>
                    </div>
                    {[...result.violations, ...result.warnings].map(
                      (finding) => (
                        <p
                          key={`${result.id}-${finding.metric}`}
                          className="mt-2 flex gap-2 text-xs"
                        >
                          <TriangleAlert
                            size={13}
                            className="shrink-0 text-[var(--warning)]"
                          />
                          {finding.message}
                        </p>
                      ),
                    )}
                  </div>
                ))}
                {!gateResults.isLoading && !gateResults.data?.length && (
                  <p className="text-xs text-[var(--muted)]">
                    No gate has been evaluated yet.
                  </p>
                )}
              </div>
            </Card>
          </div>
        )}

        <Card className="overflow-hidden">
          <div className="border-b border-[var(--border)] p-5">
            <h2 className="font-semibold">Case runs</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Each row is tied to one immutable dataset item and its generated
              trace.
            </p>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {runs.data?.items.map((run) => (
              <article key={run.id} className="p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-[var(--accent)]">
                      #{run.ordinal}
                    </span>
                    <span
                      className={`font-mono text-[10px] ${statusClass(run.status)}`}
                    >
                      {run.status}
                    </span>
                    {run.evaluation_score != null && (
                      <span className="text-xs text-[var(--muted)]">
                        {(Number(run.evaluation_score) * 100).toFixed(0)}% score
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
                    <span>{run.latency_ms ?? 0} ms</span>
                    <span>{run.total_tokens} tokens</span>
                    {run.trace_id && (
                      <Link
                        href={`/traces/${run.trace_id}`}
                        className="flex items-center gap-1 text-[var(--accent)] hover:underline"
                      >
                        Trace <ExternalLink size={12} />
                      </Link>
                    )}
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <div>
                    <Label>Input</Label>
                    <JsonValue value={run.input} />
                  </div>
                  <div>
                    <Label>Expected</Label>
                    <JsonValue value={run.expected_output} />
                  </div>
                  <div>
                    <Label>Output</Label>
                    <JsonValue value={run.output} />
                  </div>
                </div>
                {run.error_message && (
                  <p className="mt-3 text-sm text-[var(--danger)]">
                    {run.error_type}: {run.error_message}
                  </p>
                )}
              </article>
            ))}
          </div>
          {runs.data && runs.data.total_pages > 1 && (
            <div className="flex items-center justify-between border-t border-[var(--border)] p-4">
              <Button
                variant="outline"
                disabled={!runs.data.has_previous}
                onClick={() => setPage((value) => value - 1)}
              >
                <ChevronLeft size={15} className="mr-1" /> Previous
              </Button>
              <span className="text-xs text-[var(--muted)]">
                Page {page} of {runs.data.total_pages}
              </span>
              <Button
                variant="outline"
                disabled={!runs.data.has_next}
                onClick={() => setPage((value) => value + 1)}
              >
                Next <ChevronRight size={15} className="ml-1" />
              </Button>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}

export default function ExperimentDetailPage() {
  return (
    <Suspense fallback={<PageLoader label="Loading experiment" />}>
      <ExperimentDetail />
    </Suspense>
  );
}
