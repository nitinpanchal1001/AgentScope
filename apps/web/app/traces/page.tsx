"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, Card, Input, Label } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

type Organization = { id: string; name: string };
type Project = { id: string; name: string; organization_id: string };
type Environment = { id: string; name: string; slug: string };
type Trace = {
  id: string;
  external_trace_id: string;
  project_id: string;
  environment_id: string;
  environment: string;
  name: string;
  status: string;
  started_at: string;
  latency_ms: number | null;
  total_tokens: number;
  total_cost: string;
  agent_version: string | null;
  error_type: string | null;
};
type TracePage = { items: Trace[]; next_cursor: string | null };

function statusClass(status: string) {
  if (status === "SUCCESS")
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  if (status === "ERROR") return "border-red-400/30 bg-red-400/10 text-red-300";
  if (status === "RUNNING")
    return "border-sky-400/30 bg-sky-400/10 text-sky-300";
  return "border-[var(--border)] text-[var(--muted)]";
}

export default function TracesPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [status, setStatus] = useState("");
  const [agentVersion, setAgentVersion] = useState("");
  const [model, setModel] = useState("");
  const [spanType, setSpanType] = useState("");
  const [tag, setTag] = useState("");
  const [startedAfter, setStartedAfter] = useState("");
  const [startedBefore, setStartedBefore] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setReady(true));
  }, [clear, router, token]);

  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiFetch<Organization[]>("/api/v1/organizations"),
    enabled: ready,
  });
  const activeOrganizationId =
    organizationId || organizations.data?.[0]?.id || "";
  const projects = useQuery({
    queryKey: ["projects", activeOrganizationId],
    queryFn: () =>
      apiFetch<Project[]>(
        `/api/v1/organizations/${activeOrganizationId}/projects`,
      ),
    enabled: Boolean(activeOrganizationId),
  });
  const activeProjectId = projectId || projects.data?.[0]?.id || "";
  const environments = useQuery({
    queryKey: ["environments", activeProjectId],
    queryFn: () =>
      apiFetch<Environment[]>(
        `/api/v1/projects/${activeProjectId}/environments`,
      ),
    enabled: Boolean(activeProjectId),
  });

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: "50" });
    if (cursor) params.set("cursor", cursor);
    if (environmentId) params.set("environment_id", environmentId);
    if (status) params.set("status", status);
    if (agentVersion) params.set("agent_version", agentVersion);
    if (model) params.set("model", model);
    if (spanType) params.set("span_type", spanType);
    if (tag) params.set("tag", tag);
    if (startedAfter)
      params.set("started_after", new Date(startedAfter).toISOString());
    if (startedBefore)
      params.set("started_before", new Date(startedBefore).toISOString());
    return params.toString();
  }, [
    agentVersion,
    cursor,
    environmentId,
    model,
    spanType,
    startedAfter,
    startedBefore,
    status,
    tag,
  ]);

  const traces = useQuery({
    queryKey: ["traces", activeProjectId, queryString],
    queryFn: () =>
      apiFetch<TracePage>(
        `/api/v1/projects/${activeProjectId}/traces?${queryString}`,
      ),
    enabled: Boolean(activeProjectId),
    refetchInterval: 5000,
  });

  const resetPaging = () => {
    setCursor(null);
    setHistory([]);
  };

  if (!ready || organizations.isLoading)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--muted)]">
        Loading traces…
      </div>
    );

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link
              href="/dashboard"
              className="mb-3 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-white"
            >
              <ArrowLeft size={15} /> Workspace
            </Link>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--accent)]">
              Tracing / Explorer
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Agent traces</h1>
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <Activity size={15} className="text-[var(--accent)]" /> Refreshes
            every 5 seconds
          </div>
        </div>

        <Card className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <Label>Organization</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
              value={activeOrganizationId}
              onChange={(event) => {
                setOrganizationId(event.target.value);
                setProjectId("");
                resetPaging();
              }}
            >
              {organizations.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Project</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
              value={activeProjectId}
              onChange={(event) => {
                setProjectId(event.target.value);
                setEnvironmentId("");
                resetPaging();
              }}
            >
              {projects.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Environment</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
              value={environmentId}
              onChange={(event) => {
                setEnvironmentId(event.target.value);
                resetPaging();
              }}
            >
              <option value="">All environments</option>
              {environments.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Status</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                resetPaging();
              }}
            >
              <option value="">All statuses</option>
              {["RUNNING", "SUCCESS", "ERROR", "CANCELLED"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </div>
          <div>
            <Label>Agent version</Label>
            <Input
              placeholder="v2.1.0"
              value={agentVersion}
              onChange={(event) => {
                setAgentVersion(event.target.value);
                resetPaging();
              }}
            />
          </div>
          <div>
            <Label>Model</Label>
            <Input
              placeholder="gpt-4.1"
              value={model}
              onChange={(event) => {
                setModel(event.target.value);
                resetPaging();
              }}
            />
          </div>
          <div>
            <Label>Span type</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
              value={spanType}
              onChange={(event) => {
                setSpanType(event.target.value);
                resetPaging();
              }}
            >
              <option value="">All span types</option>
              {[
                "AGENT",
                "LLM",
                "TOOL",
                "RETRIEVAL",
                "EMBEDDING",
                "CHAIN",
                "CUSTOM",
              ].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </div>
          <div>
            <Label>Started after</Label>
            <Input
              type="datetime-local"
              value={startedAfter}
              onChange={(event) => {
                setStartedAfter(event.target.value);
                resetPaging();
              }}
            />
          </div>
          <div>
            <Label>Started before</Label>
            <Input
              type="datetime-local"
              value={startedBefore}
              onChange={(event) => {
                setStartedBefore(event.target.value);
                resetPaging();
              }}
            />
          </div>
          <div>
            <Label>Tag</Label>
            <Input
              placeholder="production"
              value={tag}
              onChange={(event) => {
                setTag(event.target.value);
                resetPaging();
              }}
            />
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--border)] p-5">
            <div>
              <h2 className="font-semibold">Trace stream</h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Newest executions first
              </p>
            </div>
            <Search size={17} className="text-[var(--muted)]" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left text-sm">
              <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                <tr>
                  {[
                    "Trace",
                    "Environment",
                    "Version",
                    "Status",
                    "Score",
                    "Latency",
                    "Tokens",
                    "Cost",
                    "Started",
                  ].map((heading) => (
                    <th key={heading} className="px-5 py-3 font-medium">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {traces.data?.items.map((trace) => (
                  <tr key={trace.id} className="hover:bg-white/[0.025]">
                    <td className="px-5 py-4">
                      <Link
                        href={`/traces/${trace.id}`}
                        className="font-medium hover:text-[var(--accent)]"
                      >
                        <span className="block">{trace.name}</span>
                        <span className="font-mono text-[11px] text-[var(--muted)]">
                          {trace.external_trace_id.slice(0, 12)}…
                        </span>
                      </Link>
                    </td>
                    <td className="px-5 py-4 font-mono text-xs">
                      {trace.environment}
                    </td>
                    <td className="px-5 py-4 text-[var(--muted)]">
                      {trace.agent_version ?? "—"}
                    </td>
                    <td className="px-5 py-4">
                      <span
                        className={`rounded-full border px-2 py-1 text-[11px] ${statusClass(trace.status)}`}
                      >
                        {trace.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-[var(--muted)]">—</td>
                    <td className="px-5 py-4">
                      {trace.latency_ms == null
                        ? "—"
                        : `${trace.latency_ms} ms`}
                    </td>
                    <td className="px-5 py-4">
                      {trace.total_tokens.toLocaleString()}
                    </td>
                    <td className="px-5 py-4">
                      ${Number(trace.total_cost).toFixed(4)}
                    </td>
                    <td className="px-5 py-4 text-xs text-[var(--muted)]">
                      {new Date(trace.started_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!traces.isLoading && !traces.data?.items.length && (
            <div className="p-12 text-center text-sm text-[var(--muted)]">
              No traces match these filters. Run an instrumented agent with this
              project&apos;s API key.
            </div>
          )}
          {traces.error && (
            <div className="p-5 text-sm text-[var(--danger)]">
              {traces.error.message}
            </div>
          )}
          <div className="flex justify-end gap-2 border-t border-[var(--border)] p-4">
            <Button
              variant="outline"
              disabled={!history.length}
              onClick={() => {
                const previous = [...history];
                setCursor(previous.pop() ?? null);
                setHistory(previous);
              }}
            >
              <ChevronLeft size={15} className="mr-1" /> Previous
            </Button>
            <Button
              variant="outline"
              disabled={!traces.data?.next_cursor}
              onClick={() => {
                setHistory((items) => [...items, cursor]);
                setCursor(traces.data?.next_cursor ?? null);
              }}
            >
              Next <ChevronRight size={15} className="ml-1" />
            </Button>
          </div>
        </Card>
      </div>
    </main>
  );
}
