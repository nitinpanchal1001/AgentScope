"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Clock3, Coins, Cpu, Hash, Layers3 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui";
import { API_URL, apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

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
  error_type: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  tags: string[];
};

type TraceDetail = {
  id: string;
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

type SpanNode = Span & { children: SpanNode[] };

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg border border-[var(--border)] bg-[#090c12] p-4 text-xs leading-6 text-[#c7d0df]">
      {value == null ? "—" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function statusColor(status: string) {
  if (status === "SUCCESS") return "text-emerald-300";
  if (status === "ERROR") return "text-red-300";
  if (status === "RUNNING") return "text-sky-300";
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
          className={`grid w-full grid-cols-[minmax(170px,0.7fr)_1.3fr_80px] items-center gap-4 border-b border-[var(--border)] px-4 py-3 text-left hover:bg-white/[0.025] ${selectedId === span.id ? "bg-emerald-400/[0.06]" : ""}`}
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
          <div className="relative h-5 rounded bg-white/[0.035]">
            <span
              className={`absolute top-1 h-3 rounded ${span.status === "ERROR" ? "bg-red-400/60" : "bg-emerald-400/60"}`}
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

  if (!ready || trace.isLoading)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
        Loading trace…
      </div>
    );
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
    { label: "Spans", value: data.spans.length.toString(), icon: Layers3 },
  ];

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <Link
            href="/traces"
            className="mb-4 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-white"
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

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map(({ label, value, icon: Icon }) => (
            <Card key={label} className="p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-[var(--muted)]">
                <Icon size={14} /> {label}
              </div>
              <p className="mt-3 text-xl font-semibold">{value}</p>
            </Card>
          ))}
        </div>

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
              <div className="mt-5 rounded-lg border border-red-400/30 bg-red-400/[0.06] p-4 text-sm text-red-200">
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
            <h2 className="mb-4 flex items-center gap-2 font-semibold">
              <Cpu size={16} /> Errors
            </h2>
            {data.error_message ? (
              <div className="rounded-lg border border-red-400/30 bg-red-400/[0.06] p-4 text-sm text-red-200">
                {data.error_type}: {data.error_message}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">
                No trace-level error was recorded.
              </p>
            )}
          </Card>
        </div>
      </div>
    </main>
  );
}
