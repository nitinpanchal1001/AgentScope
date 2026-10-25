"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Beaker,
  CheckCircle2,
  Clock3,
  Coins,
  Cpu,
  GitCompareArrows,
  Hash,
  Layers3,
  RotateCcw,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { API_URL, apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { type FailureRecord, type SimilarFailure } from "@/lib/failures";
import { type ReplayComparison, type TraceReplay } from "@/lib/replays";

type Span = {
  id: string;
  external_span_id: string;
  parent_span_id: string | null;
  type: string;
  name: string;
  provider: string | null;
  model: string | null;
  input: unknown;
  output: unknown;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: string;
  status: string;
  threshold: string;
  error_type: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  tags: string[];
};

type TraceDetail = {
  id: string;
  project_id: string;
  external_trace_id: string;
  name: string;
  environment: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_cost: string;
  evaluation_score: string | null;
  agent_version: string | null;
  session_id: string | null;
  user_identifier: string | null;
  input: unknown;
  output: unknown;
  metadata: Record<string, unknown>;
  tags: string[];
  error_type: string | null;
  error_message: string | null;
  spans: Span[];
};

type EvaluationResult = {
  id: string;
  evaluator_name: string;
  evaluator_version: number;
  evaluator_type: string;
  source: string;
  status: string;
  score: string | null;
  passed: boolean | null;
  label: string | null;
  reason: string | null;
  evidence: unknown[];
  error_message: string | null;
};
type Evaluator = { versions: { id: string; version: number }[] };

type SpanNode = Span & { children: SpanNode[] };

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-xl border border-[var(--border)] bg-[var(--code)] p-4 text-xs leading-6 text-[var(--code-text)]">
      {value == null ? "—" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function statusColor(status: string) {
  if (status === "SUCCESS") return "text-[var(--success)]";
  if (status === "ERROR") return "text-[var(--danger)]";
  if (status === "RUNNING") return "text-[var(--info)]";
  return "text-[var(--muted)]";
}

function SpanRows({
  nodes,
  depth,
  trace,
  selectedId,
  onSelect,
}: {
  nodes: SpanNode[];
  depth: number;
  trace: TraceDetail;
  selectedId?: string;
  onSelect: (span: Span) => void;
}) {
  const duration = Math.max(trace.latency_ms ?? 1, 1);
  const traceStart = new Date(trace.started_at).getTime();
  return nodes.map((span) => {
    const offset = Math.max(
      0,
      ((new Date(span.started_at).getTime() - traceStart) / duration) * 100,
    );
    const width = Math.max(1.5, ((span.latency_ms ?? 1) / duration) * 100);
    return (
      <div key={span.id}>
        <button
          className={`grid w-full grid-cols-[minmax(170px,0.7fr)_1.3fr_80px] items-center gap-4 border-b border-[var(--border)] px-4 py-3 text-left transition-colors hover:bg-[var(--hover)] ${selectedId === span.id ? "bg-[var(--accent-soft)]" : ""}`}
          onClick={() => onSelect(span)}
        >
          <div style={{ paddingLeft: `${depth * 18}px` }}>
            <span className="block truncate text-sm font-medium">
              {span.name}
            </span>
            <span className="font-mono text-[10px] text-[var(--muted)]">
              {span.type} {span.model ? `· ${span.model}` : ""}
            </span>
          </div>
          <div className="relative h-5 rounded bg-[var(--surface-muted)]">
            <span
              className={`absolute top-1 h-3 rounded ${span.status === "ERROR" ? "bg-[var(--danger)]" : "bg-[var(--success)]"}`}
              style={{
                left: `${Math.min(offset, 98)}%`,
                width: `${Math.min(width, 100 - Math.min(offset, 98))}%`,
              }}
            />
          </div>
          <span className="text-right font-mono text-xs text-[var(--muted)]">
            {span.latency_ms == null ? "running" : `${span.latency_ms} ms`}
          </span>
        </button>
        {span.children.length > 0 && (
          <SpanRows
            nodes={span.children}
            depth={depth + 1}
            trace={trace}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        )}
      </div>
    );
  });
}

export default function TraceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [selectedSpanId, setSelectedSpanId] = useState<string>();
  const [replayEndpoint, setReplayEndpoint] = useState("");
  const [replayModel, setReplayModel] = useState("");
  const [replayPrompt, setReplayPrompt] = useState("");
  const [replayAgentVersion, setReplayAgentVersion] = useState("");
  const [replayTemperature, setReplayTemperature] = useState("");
  const [replayParameters, setReplayParameters] = useState("{}");
  const [replayHeaders, setReplayHeaders] = useState("{}");
  const [selectedReplayId, setSelectedReplayId] = useState("");
  const [replayFormError, setReplayFormError] = useState("");
  const [similarFailures, setSimilarFailures] = useState<SimilarFailure[]>([]);

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setReady(true));
  }, [clear, router, token]);

  const trace = useQuery({
    queryKey: ["trace", params.id],
    queryFn: () => apiFetch<TraceDetail>(`/api/v1/traces/${params.id}`),
    enabled: ready,
  });
  const evaluations = useQuery({
    queryKey: ["trace-evaluations", trace.data?.project_id, params.id],
    queryFn: () =>
      apiFetch<EvaluationResult[]>(
        `/api/v1/projects/${trace.data!.project_id}/traces/${params.id}/evaluations`,
      ),
    enabled: Boolean(trace.data?.project_id),
    refetchInterval: (query) =>
      query.state.data?.some((item) =>
        ["PENDING", "RUNNING"].includes(item.status),
      )
        ? 2000
        : false,
  });
  const evaluators = useQuery({
    queryKey: ["evaluators", trace.data?.project_id],
    queryFn: () =>
      apiFetch<Evaluator[]>(
        `/api/v1/projects/${trace.data!.project_id}/evaluators`,
      ),
    enabled: Boolean(trace.data?.project_id),
  });
  const runEvaluations = useMutation({
    mutationFn: (versionIds: string[]) =>
      apiFetch<EvaluationResult[]>(
        `/api/v1/projects/${trace.data!.project_id}/traces/${params.id}/evaluations`,
        {
          method: "POST",
          body: JSON.stringify({ evaluator_version_ids: versionIds }),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["trace-evaluations", trace.data?.project_id, params.id],
      }),
  });
  const replays = useQuery({
    queryKey: ["trace-replays", trace.data?.project_id, params.id],
    queryFn: () =>
      apiFetch<TraceReplay[]>(
        `/api/v1/projects/${trace.data!.project_id}/traces/${params.id}/replays`,
      ),
    enabled: Boolean(trace.data?.project_id),
    refetchInterval: (query) =>
      query.state.data?.some((item) =>
        ["RUNNING", "EVALUATING"].includes(item.status),
      )
        ? 2000
        : false,
  });
  const activeReplayId = selectedReplayId || replays.data?.[0]?.id || "";
  const activeReplay = replays.data?.find((item) => item.id === activeReplayId);
  const replayComparison = useQuery({
    queryKey: ["replay-comparison", trace.data?.project_id, activeReplayId],
    queryFn: () =>
      apiFetch<ReplayComparison>(
        `/api/v1/projects/${trace.data!.project_id}/replays/${activeReplayId}/comparison`,
      ),
    enabled: Boolean(trace.data?.project_id && activeReplay?.replay_trace_id),
    refetchInterval: activeReplay?.status === "EVALUATING" ? 2000 : false,
  });
  const createReplay = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<TraceReplay>(
        `/api/v1/projects/${trace.data!.project_id}/traces/${params.id}/replays`,
        { method: "POST", body: JSON.stringify(body) },
      ),
    onSuccess: (replay) => {
      setSelectedReplayId(replay.id);
      setReplayFormError("");
      queryClient.invalidateQueries({
        queryKey: ["trace-replays", trace.data?.project_id, params.id],
      });
    },
  });
  const analyzeFailure = useMutation({
    mutationFn: () =>
      apiFetch<FailureRecord | null>(
        `/api/v1/projects/${trace.data!.project_id}/traces/${params.id}/failure-analysis`,
        { method: "POST" },
      ),
    onSuccess: async (failure) => {
      if (!failure) return;
      const results = await apiFetch<SimilarFailure[]>(
        `/api/v1/projects/${trace.data!.project_id}/failures/search`,
        {
          method: "POST",
          body: JSON.stringify({ query: failure.document, limit: 6 }),
        },
      );
      setSimilarFailures(
        results.filter((item) => item.failure.trace_id !== params.id),
      );
    },
  });

  const submitReplay = () => {
    try {
      const parameters = JSON.parse(replayParameters) as Record<
        string,
        unknown
      >;
      const headersFromEnv = JSON.parse(replayHeaders) as Record<
        string,
        string
      >;
      createReplay.mutate({
        agent: {
          endpoint: replayEndpoint,
          headers_from_env: headersFromEnv,
        },
        overrides: {
          model: replayModel || null,
          prompt_version: replayPrompt || null,
          agent_version: replayAgentVersion || null,
          temperature:
            replayTemperature === "" ? null : Number(replayTemperature),
          parameters,
        },
      });
    } catch {
      setReplayFormError(
        "Parameters and header mappings must be valid JSON objects.",
      );
    }
  };

  useEffect(() => {
    if (!ready || !token || trace.data?.status !== "RUNNING") return;
    const controller = new AbortController();
    const stream = async () => {
      const response = await fetch(
        `${API_URL}/api/v1/traces/${params.id}/events`,
        {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        },
      );
      if (!response.ok || !response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const messages = buffer.split("\n\n");
        buffer = messages.pop() ?? "";
        for (const message of messages) {
          const data = message
            .split("\n")
            .find((line) => line.startsWith("data: "))
            ?.slice(6);
          if (data && data !== "{}")
            queryClient.setQueryData(["trace", params.id], JSON.parse(data));
        }
      }
    };
    stream().catch(() => undefined);
    return () => controller.abort();
  }, [params.id, queryClient, ready, token, trace.data?.status]);

  const tree = useMemo(() => {
    if (!trace.data) return [];
    const nodes = new Map<string, SpanNode>();
    trace.data.spans.forEach((span) =>
      nodes.set(span.id, { ...span, children: [] }),
    );
    const roots: SpanNode[] = [];
    nodes.forEach((node) => {
      const parent = node.parent_span_id
        ? nodes.get(node.parent_span_id)
        : undefined;
      if (parent) parent.children.push(node);
      else roots.push(node);
    });
    return roots;
  }, [trace.data]);

  const selectedSpan = trace.data?.spans.find(
    (span) => span.id === selectedSpanId,
  );

  if (!ready || trace.isLoading) return <PageLoader label="Loading trace" />;
  if (trace.error || !trace.data)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--danger)]">
        {trace.error?.message ?? "Trace not found"}
      </div>
    );

  const data = trace.data;
  const metrics = [
    {
      label: "Duration",
      value: data.latency_ms == null ? "Running" : `${data.latency_ms} ms`,
      icon: Clock3,
    },
    { label: "Tokens", value: data.total_tokens.toLocaleString(), icon: Hash },
    {
      label: "Cost",
      value: `$${Number(data.total_cost).toFixed(6)}`,
      icon: Coins,
    },
    {
      label: "Evaluation",
      value:
        data.evaluation_score == null
          ? "Not scored"
          : `${(Number(data.evaluation_score) * 100).toFixed(0)}%`,
      icon: Beaker,
    },
    { label: "Spans", value: data.spans.length.toString(), icon: Layers3 },
  ];

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <Link
            href="/traces"
            className="mb-4 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <ArrowLeft size={15} /> Trace explorer
          </Link>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="font-mono text-xs text-[var(--accent)]">
                {data.external_trace_id}
              </p>
              <h1 className="mt-2 text-3xl font-semibold">{data.name}</h1>
              <p className="mt-2 text-sm text-[var(--muted)]">
                {data.environment} · {data.agent_version ?? "unversioned"} ·{" "}
                {new Date(data.started_at).toLocaleString()}
              </p>
            </div>
            <span
              className={`rounded-full border border-current/30 px-3 py-1 text-xs font-semibold ${statusColor(data.status)}`}
            >
              {data.status}
            </span>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {metrics.map(({ label, value, icon: Icon }) => (
            <Card key={label} className="p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-[var(--muted)]">
                <Icon size={14} /> {label}
              </div>
              <p className="mt-3 text-xl font-semibold">{value}</p>
            </Card>
          ))}
        </div>

        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--border)] p-5">
            <div>
              <h2 className="flex items-center gap-2 font-semibold">
                <Beaker size={16} className="text-[var(--accent)]" /> Evaluation
                results
              </h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Versioned scores with reasons and evidence.
              </p>
            </div>
            <Button
              variant="outline"
              disabled={runEvaluations.isPending || !evaluators.data?.length}
              loading={runEvaluations.isPending}
              onClick={() =>
                runEvaluations.mutate(
                  evaluators.data
                    ?.map((item) => item.versions[0]?.id)
                    .filter((id): id is string => Boolean(id)) ?? [],
                )
              }
            >
              Run latest evaluators
            </Button>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {evaluations.data?.map((result) => (
              <div key={result.id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    {result.passed === true ? (
                      <CheckCircle2
                        size={18}
                        className="mt-0.5 text-[var(--success)]"
                      />
                    ) : result.passed === false ? (
                      <XCircle
                        size={18}
                        className="mt-0.5 text-[var(--danger)]"
                      />
                    ) : (
                      <Clock3 size={18} className="mt-0.5 text-[var(--info)]" />
                    )}
                    <div>
                      <p className="font-medium">{result.evaluator_name}</p>
                      <p className="mt-1 font-mono text-[11px] text-[var(--muted)]">
                        v{result.evaluator_version} · {result.evaluator_type} ·{" "}
                        {result.source}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full border border-[var(--border)] px-2 py-1 text-xs">
                    {result.score == null
                      ? result.status
                      : `${(Number(result.score) * 100).toFixed(0)}% · ${result.label}`}
                  </span>
                </div>
                {(result.reason || result.error_message) && (
                  <p className="mt-3 text-sm text-[var(--muted)]">
                    {result.reason || result.error_message}
                  </p>
                )}
                {result.evidence.length > 0 && (
                  <details className="mt-3 text-xs text-[var(--muted)]">
                    <summary className="cursor-pointer">Evidence</summary>
                    <JsonBlock value={result.evidence} />
                  </details>
                )}
              </div>
            ))}
            {!evaluations.isLoading && !evaluations.data?.length && (
              <div className="p-8 text-sm text-[var(--muted)]">
                No evaluation results yet. Create an evaluator and run it here,
                or bind it to this trace&apos;s environment for automatic
                scoring.
              </div>
            )}
          </div>
          {(evaluations.error || runEvaluations.error) && (
            <p className="border-t border-[var(--border)] p-4 text-sm text-[var(--danger)]">
              {evaluations.error?.message || runEvaluations.error?.message}
            </p>
          )}
        </Card>

        <Card className="overflow-hidden">
          <div className="border-b border-[var(--border)] p-5">
            <h2 className="flex items-center gap-2 font-semibold">
              <RotateCcw size={16} className="text-[var(--accent)]" /> Replay
              trace
            </h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Execute the original input with controlled overrides. The
              production trace is never changed.
            </p>
          </div>
          <div className="grid gap-6 p-5 xl:grid-cols-[0.8fr_1.2fr]">
            <div className="space-y-4">
              <div>
                <Label>Agent endpoint</Label>
                <Input
                  required
                  type="url"
                  value={replayEndpoint}
                  onChange={(event) => setReplayEndpoint(event.target.value)}
                  placeholder="https://candidate.example.com/invoke"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Model override</Label>
                  <Input
                    value={replayModel}
                    onChange={(event) => setReplayModel(event.target.value)}
                    placeholder="candidate-model"
                  />
                </div>
                <div>
                  <Label>Prompt version</Label>
                  <Input
                    value={replayPrompt}
                    onChange={(event) => setReplayPrompt(event.target.value)}
                    placeholder="support-v2"
                  />
                </div>
                <div>
                  <Label>Agent version</Label>
                  <Input
                    value={replayAgentVersion}
                    onChange={(event) =>
                      setReplayAgentVersion(event.target.value)
                    }
                  />
                </div>
                <div>
                  <Label>Temperature</Label>
                  <Input
                    type="number"
                    min={0}
                    max={2}
                    step="any"
                    value={replayTemperature}
                    onChange={(event) =>
                      setReplayTemperature(event.target.value)
                    }
                  />
                </div>
              </div>
              <div>
                <Label>Other parameters (JSON)</Label>
                <Input
                  value={replayParameters}
                  onChange={(event) => setReplayParameters(event.target.value)}
                />
              </div>
              <div>
                <Label>Header → environment variable mappings (JSON)</Label>
                <Input
                  value={replayHeaders}
                  onChange={(event) => setReplayHeaders(event.target.value)}
                  placeholder='{"Authorization":"CANDIDATE_AGENT_AUTH"}'
                />
                <p className="mt-1 text-[10px] text-[var(--muted)]">
                  Store environment variable names only. Secret values stay in
                  the worker.
                </p>
              </div>
              {(replayFormError || createReplay.error) && (
                <p className="text-sm text-[var(--danger)]">
                  {replayFormError || createReplay.error?.message}
                </p>
              )}
              <Button
                disabled={
                  !replayEndpoint ||
                  createReplay.isPending ||
                  data.status === "RUNNING"
                }
                loading={createReplay.isPending}
                onClick={submitReplay}
              >
                <RotateCcw size={15} className="mr-2" /> Run replay
              </Button>
            </div>

            <div>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-64 flex-1">
                  <Label>Replay history</Label>
                  <select
                    className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
                    value={activeReplayId}
                    onChange={(event) =>
                      setSelectedReplayId(event.target.value)
                    }
                  >
                    {replays.data?.map((replay) => (
                      <option key={replay.id} value={replay.id}>
                        {new Date(replay.created_at).toLocaleString()} ·{" "}
                        {replay.status}
                      </option>
                    ))}
                  </select>
                </div>
                {activeReplay?.replay_trace_id && (
                  <Button variant="outline" asChild>
                    <Link href={`/traces/${activeReplay.replay_trace_id}`}>
                      Open replay trace
                    </Link>
                  </Button>
                )}
              </div>
              {activeReplay?.error_message && (
                <p className="mt-3 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]">
                  {activeReplay.error_type}: {activeReplay.error_message}
                </p>
              )}
              {replayComparison.data ? (
                <div className="mt-4 space-y-4">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                    <GitCompareArrows
                      size={15}
                      className="text-[var(--accent)]"
                    />{" "}
                    Original vs replay
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <Label>Original output</Label>
                      <JsonBlock
                        value={replayComparison.data.original.output}
                      />
                    </div>
                    <div>
                      <Label>Replay output</Label>
                      <JsonBlock value={replayComparison.data.replay.output} />
                    </div>
                  </div>
                  <div className="overflow-x-auto rounded-md border border-[var(--border)]">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-[var(--border)] text-[var(--muted)]">
                        <tr>
                          <th className="px-3 py-2">Metric</th>
                          <th className="px-3 py-2">Original</th>
                          <th className="px-3 py-2">Replay</th>
                          <th className="px-3 py-2">Delta</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        <tr>
                          <td className="px-3 py-2">Evaluation</td>
                          <td className="px-3 py-2">
                            {replayComparison.data.original.evaluation_score ??
                              "—"}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.replay.evaluation_score ??
                              "—"}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.differences
                              .evaluation_score_delta ?? "—"}
                          </td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2">Latency (ms)</td>
                          <td className="px-3 py-2">
                            {replayComparison.data.original.latency_ms ?? "—"}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.replay.latency_ms ?? "—"}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.differences
                              .latency_ms_delta ?? "—"}
                          </td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2">Cost</td>
                          <td className="px-3 py-2">
                            ${replayComparison.data.original.total_cost}
                          </td>
                          <td className="px-3 py-2">
                            ${replayComparison.data.replay.total_cost}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.differences.total_cost_delta}
                          </td>
                        </tr>
                        <tr>
                          <td className="px-3 py-2">Tokens</td>
                          <td className="px-3 py-2">
                            {replayComparison.data.original.total_tokens}
                          </td>
                          <td className="px-3 py-2">
                            {replayComparison.data.replay.total_tokens}
                          </td>
                          <td className="px-3 py-2">
                            {
                              replayComparison.data.differences
                                .total_tokens_delta
                            }
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <Label>Tool sequence</Label>
                      <JsonBlock
                        value={{
                          original:
                            replayComparison.data.original.tool_sequence,
                          replay: replayComparison.data.replay.tool_sequence,
                          changed:
                            replayComparison.data.differences
                              .tool_sequence_changed,
                        }}
                      />
                    </div>
                    <div>
                      <Label>Span structure</Label>
                      <JsonBlock
                        value={{
                          original:
                            replayComparison.data.original.span_structure,
                          replay: replayComparison.data.replay.span_structure,
                          changed:
                            replayComparison.data.differences
                              .span_structure_changed,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-5 text-sm text-[var(--muted)]">
                  {activeReplay
                    ? `Replay status: ${activeReplay.status}. Comparison appears after invocation.`
                    : "No replays yet."}
                </p>
              )}
            </div>
          </div>
        </Card>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card className="p-5">
            <h2 className="mb-4 font-semibold">Input</h2>
            <JsonBlock value={data.input} />
          </Card>
          <Card className="p-5">
            <h2 className="mb-4 font-semibold">Output</h2>
            <JsonBlock value={data.output} />
          </Card>
        </div>

        <Card className="overflow-hidden">
          <div className="border-b border-[var(--border)] p-5">
            <h2 className="font-semibold">Execution timeline</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Select a span to inspect its payload and error details.
            </p>
          </div>
          {tree.length ? (
            <SpanRows
              nodes={tree}
              depth={0}
              trace={data}
              selectedId={selectedSpanId}
              onSelect={(span) => setSelectedSpanId(span.id)}
            />
          ) : (
            <div className="p-8 text-sm text-[var(--muted)]">
              No spans were recorded for this trace.
            </div>
          )}
        </Card>

        {selectedSpan && (
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wider text-[var(--muted)]">
                  Selected span
                </p>
                <h2 className="mt-1 text-lg font-semibold">
                  {selectedSpan.name}
                </h2>
              </div>
              <span className="font-mono text-xs text-[var(--muted)]">
                {selectedSpan.type} · {selectedSpan.provider ?? "—"} /{" "}
                {selectedSpan.model ?? "—"}
              </span>
            </div>
            <div className="mt-5 grid gap-5 xl:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-medium">Input</h3>
                <JsonBlock value={selectedSpan.input} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-medium">Output</h3>
                <JsonBlock value={selectedSpan.output} />
              </div>
            </div>
            {selectedSpan.error_message && (
              <div className="mt-5 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] p-4 text-sm text-[var(--danger)]">
                {selectedSpan.error_type}: {selectedSpan.error_message}
              </div>
            )}
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-medium">Metadata</h3>
              <JsonBlock value={selectedSpan.metadata} />
            </div>
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-2">
          <Card className="p-5">
            <h2 className="mb-4 font-semibold">Trace metadata</h2>
            <JsonBlock
              value={{
                ...data.metadata,
                tags: data.tags,
                session_id: data.session_id,
                user_identifier: data.user_identifier,
              }}
            />
          </Card>
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 font-semibold">
                <Cpu size={16} /> Failure intelligence
              </h2>
              <Button
                variant="outline"
                disabled={data.status === "RUNNING" || analyzeFailure.isPending}
                loading={analyzeFailure.isPending}
                onClick={() => analyzeFailure.mutate()}
              >
                Analyze failure
              </Button>
            </div>
            {data.error_message ? (
              <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] p-4 text-sm text-[var(--danger)]">
                {data.error_type}: {data.error_message}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">
                No trace-level error was recorded.
              </p>
            )}
            {analyzeFailure.data === null && (
              <p className="mt-3 text-xs text-[var(--muted)]">
                This trace does not currently meet a supported failure
                definition.
              </p>
            )}
            {similarFailures.length > 0 && (
              <div className="mt-4 border-t border-[var(--border)] pt-4">
                <Label>Semantically similar failures</Label>
                <div className="space-y-2">
                  {similarFailures.map((item) => (
                    <Link
                      key={item.failure.id}
                      href={`/traces/${item.failure.trace_id}`}
                      className="flex items-center justify-between rounded-md border border-[var(--border)] p-2 text-xs transition-colors hover:bg-[var(--hover)]"
                    >
                      <span>{item.failure.title}</span>
                      <span className="font-mono text-[var(--muted)]">
                        {item.similarity.toFixed(3)}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </main>
  );
}
