"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BellRing, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import type { AlertEvent, AlertMetric, AlertRule } from "@/lib/alerts";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };
type Environment = { id: string; name: string };

const selectClass =
  "h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]";

export default function AlertsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("Production error rate");
  const [metric, setMetric] = useState<AlertMetric>("ERROR_RATE");
  const [operator, setOperator] = useState("GREATER_THAN");
  const [threshold, setThreshold] = useState("5");
  const [windowMinutes, setWindowMinutes] = useState("15");
  const [cooldownMinutes, setCooldownMinutes] = useState("30");
  const [severity, setSeverity] = useState("WARNING");
  const [channel, setChannel] = useState("WEBHOOK");
  const [channelTarget, setChannelTarget] = useState("");
  const [environmentId, setEnvironmentId] = useState("");

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
  const rules = useQuery({
    queryKey: ["alert-rules", activeProjectId],
    queryFn: () =>
      apiFetch<AlertRule[]>(`/api/v1/projects/${activeProjectId}/alert-rules`),
    enabled: Boolean(activeProjectId),
  });
  const history = useQuery({
    queryKey: ["alerts", activeProjectId],
    queryFn: () =>
      apiFetch<AlertEvent[]>(`/api/v1/projects/${activeProjectId}/alerts`),
    enabled: Boolean(activeProjectId),
    refetchInterval: 15_000,
  });
  const createRule = useMutation({
    mutationFn: () =>
      apiFetch<AlertRule>(`/api/v1/projects/${activeProjectId}/alert-rules`, {
        method: "POST",
        body: JSON.stringify({
          name,
          environment_id: environmentId || null,
          metric,
          operator,
          threshold,
          window_minutes: Number(windowMinutes),
          severity,
          enabled: true,
          channel,
          channel_target: channelTarget,
          cooldown_minutes: Number(cooldownMinutes),
        }),
      }),
    onSuccess: () => {
      setChannelTarget("");
      queryClient.invalidateQueries({
        queryKey: ["alert-rules", activeProjectId],
      });
    },
  });
  const deleteRule = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/projects/${activeProjectId}/alert-rules/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["alert-rules", activeProjectId],
      }),
  });

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading alerts" />;
  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <Link
            href="/dashboard"
            className="flex items-center gap-2 text-sm text-[var(--muted)]"
          >
            <ArrowLeft size={15} /> Workspace
          </Link>
          <p className="mt-4 text-sm font-medium text-[var(--muted)]">
            Monitoring / Alerts
          </p>
          <h1 className="mt-2 text-3xl font-semibold">
            Production alert rules
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Windowed metrics, cooldown deduplication, and delivery history.
          </p>
        </div>
        <Card className="grid gap-4 p-5 md:grid-cols-2">
          <div>
            <Label>Organization</Label>
            <select
              className={selectClass}
              value={activeOrganizationId}
              onChange={(event) => {
                setOrganizationId(event.target.value);
                setProjectId("");
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
              className={selectClass}
              value={activeProjectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              {projects.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        </Card>
        <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
          <Card className="p-5">
            <div className="flex items-center gap-2">
              <Plus size={17} className="text-[var(--accent)]" />
              <h2 className="font-semibold">New rule</h2>
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <Label>Metric</Label>
                <select
                  className={selectClass}
                  value={metric}
                  onChange={(e) => setMetric(e.target.value as AlertMetric)}
                >
                  {[
                    "ERROR_RATE",
                    "HALLUCINATION_RATE",
                    "P95_LATENCY_MS",
                    "AVERAGE_COST",
                    "EVALUATION_SCORE",
                    "TOOL_FAILURE_RATE",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Operator</Label>
                <select
                  className={selectClass}
                  value={operator}
                  onChange={(e) => setOperator(e.target.value)}
                >
                  {[
                    "GREATER_THAN",
                    "GREATER_THAN_OR_EQUAL",
                    "LESS_THAN",
                    "LESS_THAN_OR_EQUAL",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Threshold</Label>
                <Input
                  type="number"
                  step="any"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                />
              </div>
              <div>
                <Label>Environment</Label>
                <select
                  className={selectClass}
                  value={environmentId}
                  onChange={(e) => setEnvironmentId(e.target.value)}
                >
                  <option value="">All</option>
                  {environments.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Window minutes</Label>
                <Input
                  type="number"
                  value={windowMinutes}
                  onChange={(e) => setWindowMinutes(e.target.value)}
                />
              </div>
              <div>
                <Label>Cooldown minutes</Label>
                <Input
                  type="number"
                  value={cooldownMinutes}
                  onChange={(e) => setCooldownMinutes(e.target.value)}
                />
              </div>
              <div>
                <Label>Severity</Label>
                <select
                  className={selectClass}
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  {["INFO", "WARNING", "CRITICAL"].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Channel</Label>
                <select
                  className={selectClass}
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                >
                  <option>WEBHOOK</option>
                  <option>EMAIL</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <Label>
                  {channel === "EMAIL" ? "Recipient" : "Webhook URL"}
                </Label>
                <Input
                  type={channel === "EMAIL" ? "email" : "url"}
                  value={channelTarget}
                  onChange={(e) => setChannelTarget(e.target.value)}
                />
              </div>
            </div>
            {createRule.error && (
              <p className="mt-3 text-sm text-[var(--danger)]">
                {createRule.error.message}
              </p>
            )}
            <Button
              className="mt-5 w-full"
              onClick={() => createRule.mutate()}
              disabled={
                !activeProjectId || !channelTarget || createRule.isPending
              }
              loading={createRule.isPending}
            >
              <BellRing size={15} className="mr-2" /> Create alert
            </Button>
          </Card>
          <div className="space-y-6">
            <Card className="overflow-hidden">
              <div className="border-b border-[var(--border)] p-5">
                <h2 className="font-semibold">Rules</h2>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {rules.data?.map((rule) => (
                  <article
                    key={rule.id}
                    className="flex items-start justify-between gap-4 p-5"
                  >
                    <div>
                      <p className="font-semibold">{rule.name}</p>
                      <p className="mt-1 font-mono text-xs text-[var(--muted)]">
                        {rule.metric} {rule.operator} {rule.threshold} ·{" "}
                        {rule.window_minutes}m / {rule.cooldown_minutes}m
                        cooldown
                      </p>
                      <p className="mt-2 text-xs text-[var(--accent)]">
                        {rule.channel} · {rule.channel_target}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      onClick={() => deleteRule.mutate(rule.id)}
                      loading={deleteRule.isPending}
                      aria-label={`Delete ${rule.name}`}
                    >
                      <Trash2 size={15} />
                    </Button>
                  </article>
                ))}
              </div>
            </Card>
            <Card className="overflow-hidden">
              <div className="border-b border-[var(--border)] p-5">
                <h2 className="font-semibold">Alert history</h2>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {history.data?.map((event) => (
                  <article key={event.id} className="p-5">
                    <div className="flex items-center justify-between">
                      <p className="font-semibold">{event.rule_name}</p>
                      <span className="font-mono text-xs text-[var(--accent)]">
                        {event.status}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-[var(--muted)]">
                      Observed {event.observed_value} · threshold{" "}
                      {event.threshold} ·{" "}
                      {new Date(event.triggered_at).toLocaleString()}
                    </p>
                    {event.last_error && (
                      <p className="mt-2 text-xs text-[var(--danger)]">
                        {event.last_error}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}
