"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CircleDollarSign,
  Clock3,
  Gauge,
  ShieldCheck,
  Sigma,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

type Organization = { id: string; name: string };
type Project = { id: string; name: string; organization_id: string };
type Environment = { id: string; name: string; slug: string };
type Summary = {
  total_traces: number;
  success_rate: number;
  error_rate: number;
  average_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_tokens: number;
  total_cost: string;
  average_evaluation_score: number | null;
};
type Bucket = {
  started_at: string;
  trace_count: number;
  success_count: number;
  error_count: number;
  average_latency_ms: number | null;
  total_tokens: number;
  total_cost: string;
};
type Breakdown = {
  name: string;
  count: number;
  error_count: number;
  total_tokens: number;
  total_cost: string;
};
type Analytics = {
  started_after: string;
  started_before: string;
  bucket: "5m" | "1h" | "1d";
  summary: Summary;
  timeseries: Bucket[];
  models: Breakdown[];
  providers: Breakdown[];
  tools: Breakdown[];
  agents: Breakdown[];
  failure_types: Breakdown[];
};

const ranges = {
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

function formatLatency(value: number | null) {
  if (value == null) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${Math.round(value)} ms`;
}

function MetricCard({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between text-[var(--muted)]">
        <span className="text-xs font-semibold uppercase tracking-wider">
          {label}
        </span>
        {icon}
      </div>
      <p className="mt-4 text-2xl font-semibold tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-[var(--muted)]">{detail}</p>
    </Card>
  );
}

function BreakdownList({
  title,
  items,
}: {
  title: string;
  items: Breakdown[];
}) {
  return (
    <Card className="p-5">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-4 space-y-3">
        {items.slice(0, 6).map((item) => (
          <div
            key={item.name}
            className="flex items-center justify-between border-b border-[var(--border)] pb-3 text-sm last:border-0 last:pb-0"
          >
            <span className="min-w-0 truncate font-mono text-xs">
              {item.name}
            </span>
            <span className="ml-4 text-xs text-[var(--muted)]">
              {item.count.toLocaleString()} calls
            </span>
          </div>
        ))}
        {!items.length && (
          <p className="text-sm text-[var(--muted)]">No data in this range.</p>
        )}
      </div>
    </Card>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [range, setRange] = useState<keyof typeof ranges>("24h");

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
  const windowParams = useMemo(() => {
    const ended = new Date();
    const started = new Date(ended.getTime() - ranges[range]);
    const params = new URLSearchParams({
      started_after: started.toISOString(),
      started_before: ended.toISOString(),
      bucket: "auto",
    });
    if (environmentId) params.set("environment_id", environmentId);
    return params.toString();
  }, [environmentId, range]);
  const analytics = useQuery({
    queryKey: ["analytics", activeProjectId, windowParams],
    queryFn: () =>
      apiFetch<Analytics>(
        `/api/v1/projects/${activeProjectId}/analytics?${windowParams}`,
      ),
    enabled: Boolean(activeProjectId),
    refetchInterval: 30_000,
  });
  const chartData =
    analytics.data?.timeseries.map((item) => ({
      ...item,
      label: new Date(item.started_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
      cost: Number(item.total_cost),
    })) ?? [];
  const summary = analytics.data?.summary;

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading analytics" />;

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link
              href="/dashboard"
              className="mb-3 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
            >
              <ArrowLeft size={15} /> Workspace
            </Link>
            <p className="text-sm font-medium text-[var(--muted)]">
              Metrics / Operations
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Agent analytics</h1>
          </div>
        </div>

        <Card className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <Label>Organization</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={activeOrganizationId}
              onChange={(event) => {
                setOrganizationId(event.target.value);
                setProjectId("");
                setEnvironmentId("");
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
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={activeProjectId}
              onChange={(event) => {
                setProjectId(event.target.value);
                setEnvironmentId("");
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
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={environmentId}
              onChange={(event) => setEnvironmentId(event.target.value)}
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
            <Label>Time range</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={range}
              onChange={(event) =>
                setRange(event.target.value as keyof typeof ranges)
              }
            >
              <option value="6h">Last 6 hours</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
            </select>
          </div>
        </Card>

        {analytics.error && (
          <Card className="border-red-400/30 p-5 text-sm text-[var(--danger)]">
            {analytics.error.message}
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
          <MetricCard
            label="Total traces"
            value={(summary?.total_traces ?? 0).toLocaleString()}
            detail={`Bucketed by ${analytics.data?.bucket ?? "auto"}`}
            icon={<Sigma size={17} />}
          />
          <MetricCard
            label="Success rate"
            value={`${(summary?.success_rate ?? 0).toFixed(1)}%`}
            detail="Completed successfully"
            icon={<ShieldCheck size={17} />}
          />
          <MetricCard
            label="P95 latency"
            value={formatLatency(summary?.p95_latency_ms ?? null)}
            detail={`Average ${formatLatency(summary?.average_latency_ms ?? null)}`}
            icon={<Clock3 size={17} />}
          />
          <MetricCard
            label="Total tokens"
            value={(summary?.total_tokens ?? 0).toLocaleString()}
            detail="Input and output"
            icon={<Gauge size={17} />}
          />
          <MetricCard
            label="Total cost"
            value={`$${Number(summary?.total_cost ?? 0).toFixed(4)}`}
            detail="Stored historical cost"
            icon={<CircleDollarSign size={17} />}
          />
          <MetricCard
            label="Quality score"
            value={
              summary?.average_evaluation_score == null
                ? "—"
                : `${(summary.average_evaluation_score * 100).toFixed(1)}%`
            }
            detail={`${(summary?.error_rate ?? 0).toFixed(1)}% execution errors`}
            icon={<TriangleAlert size={17} />}
          />
        </div>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card className="p-5">
            <h2 className="font-semibold">Trace volume and errors</h2>
            <div className="mt-5 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="traceFill" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="5%"
                        stopColor="var(--accent)"
                        stopOpacity={0.35}
                      />
                      <stop
                        offset="95%"
                        stopColor="var(--accent)"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                  <XAxis dataKey="label" hide />
                  <YAxis allowDecimals={false} stroke="var(--muted)" />
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface-raised)",
                      border: "1px solid var(--border)",
                      color: "var(--foreground)",
                    }}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="trace_count"
                    name="Traces"
                    stroke="var(--accent)"
                    fill="url(#traceFill)"
                  />
                  <Line
                    type="monotone"
                    dataKey="error_count"
                    name="Errors"
                    stroke="var(--danger)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold">Latency and cost</h2>
            <div className="mt-5 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                  <XAxis dataKey="label" hide />
                  <YAxis yAxisId="latency" stroke="var(--muted)" />
                  <YAxis
                    yAxisId="cost"
                    orientation="right"
                    stroke="var(--muted)"
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface-raised)",
                      border: "1px solid var(--border)",
                      color: "var(--foreground)",
                    }}
                  />
                  <Legend />
                  <Line
                    yAxisId="latency"
                    type="monotone"
                    dataKey="average_latency_ms"
                    name="Average latency (ms)"
                    stroke="var(--info)"
                    dot={false}
                  />
                  <Line
                    yAxisId="cost"
                    type="monotone"
                    dataKey="cost"
                    name="Cost (USD)"
                    stroke="var(--warning)"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <Card className="p-5">
          <h2 className="font-semibold">Token usage by interval</h2>
          <div className="mt-5 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="label" hide />
                <YAxis stroke="var(--muted)" />
                <Tooltip
                  contentStyle={{
                    background: "var(--surface-raised)",
                    border: "1px solid var(--border)",
                    color: "var(--foreground)",
                  }}
                />
                <Bar
                  dataKey="total_tokens"
                  name="Tokens"
                  fill="var(--info)"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          <BreakdownList
            title="Top models"
            items={analytics.data?.models ?? []}
          />
          <BreakdownList
            title="Top providers"
            items={analytics.data?.providers ?? []}
          />
          <BreakdownList
            title="Top tools"
            items={analytics.data?.tools ?? []}
          />
          <BreakdownList
            title="Top agents"
            items={analytics.data?.agents ?? []}
          />
        </div>
      </div>
    </main>
  );
}
