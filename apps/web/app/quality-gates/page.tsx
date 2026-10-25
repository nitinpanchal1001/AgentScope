"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  GitCompareArrows,
  Plus,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import {
  QUALITY_METRICS,
  type QualityGate,
  type QualityGateRule,
} from "@/lib/quality-gates";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };

const selectClass =
  "h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]";

const defaultRule = (): QualityGateRule => ({
  metric: "pass_rate",
  constraint: "max_regression",
  threshold: 0.03,
  comparison: "absolute",
  severity: "FAIL",
});

function formatThreshold(rule: QualityGateRule) {
  if (rule.comparison === "relative")
    return `${(rule.threshold * 100).toFixed(1)}%`;
  return rule.threshold.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

export default function QualityGatesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rules, setRules] = useState<QualityGateRule[]>([defaultRule()]);

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
  const gates = useQuery({
    queryKey: ["quality-gates", activeProjectId],
    queryFn: () =>
      apiFetch<QualityGate[]>(
        `/api/v1/projects/${activeProjectId}/quality-gates`,
      ),
    enabled: Boolean(activeProjectId),
  });
  const createGate = useMutation({
    mutationFn: () =>
      apiFetch<QualityGate>(
        `/api/v1/projects/${activeProjectId}/quality-gates`,
        {
          method: "POST",
          body: JSON.stringify({
            name,
            description: description || null,
            rules,
          }),
        },
      ),
    onSuccess: () => {
      setName("");
      setDescription("");
      setRules([defaultRule()]);
      queryClient.invalidateQueries({
        queryKey: ["quality-gates", activeProjectId],
      });
    },
  });

  const updateRule = (index: number, patch: Partial<QualityGateRule>) =>
    setRules((current) =>
      current.map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, ...patch } : rule,
      ),
    );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    createGate.mutate();
  };

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading quality gates" />;

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <Link
            href="/dashboard"
            className="mb-3 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <ArrowLeft size={15} /> Workspace
          </Link>
          <p className="text-sm font-medium text-[var(--muted)]">
            Regression / Release policy
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Quality gates</h1>
          <p className="mt-2 max-w-3xl text-sm text-[var(--muted)]">
            Persist structured regression rules, then evaluate completed
            candidates against the baseline for their dataset.
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
              {organizations.data?.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}
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
              {projects.data?.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <Card className="p-5">
            <div className="mb-5 flex items-center gap-2">
              <Plus size={17} className="text-[var(--accent)]" />
              <h2 className="font-semibold">New gate</h2>
            </div>
            <form className="space-y-4" onSubmit={submit}>
              <div>
                <Label>Name</Label>
                <Input
                  required
                  maxLength={160}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Production release"
                />
              </div>
              <div>
                <Label>Description</Label>
                <textarea
                  className="min-h-20 w-full rounded-md border border-[var(--border)] bg-[var(--input)] p-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
                  maxLength={4000}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Blocks correctness regressions; warns on operational growth."
                />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="mb-0">Rules</Label>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      setRules((current) => [...current, defaultRule()])
                    }
                  >
                    <Plus size={14} className="mr-1" /> Add rule
                  </Button>
                </div>
                {rules.map((rule, index) => (
                  <div
                    key={`${index}-${rule.metric}`}
                    className="grid gap-3 rounded-md border border-[var(--border)] p-3 md:grid-cols-2"
                  >
                    <div>
                      <Label>Metric</Label>
                      <select
                        className={selectClass}
                        value={rule.metric}
                        onChange={(event) =>
                          updateRule(index, {
                            metric: event.target
                              .value as QualityGateRule["metric"],
                          })
                        }
                      >
                        {QUALITY_METRICS.map((metric) => (
                          <option key={metric.value} value={metric.value}>
                            {metric.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label>Constraint</Label>
                      <select
                        className={selectClass}
                        value={rule.constraint}
                        onChange={(event) =>
                          updateRule(index, {
                            constraint: event.target
                              .value as QualityGateRule["constraint"],
                          })
                        }
                      >
                        <option value="max_regression">
                          Maximum regression
                        </option>
                        <option value="max_increase">Maximum increase</option>
                      </select>
                    </div>
                    <div>
                      <Label>Threshold</Label>
                      <Input
                        required
                        type="number"
                        min={0}
                        step="any"
                        value={rule.threshold}
                        onChange={(event) =>
                          updateRule(index, {
                            threshold: Number(event.target.value),
                          })
                        }
                      />
                    </div>
                    <div>
                      <Label>Comparison</Label>
                      <select
                        className={selectClass}
                        value={rule.comparison}
                        onChange={(event) =>
                          updateRule(index, {
                            comparison: event.target
                              .value as QualityGateRule["comparison"],
                          })
                        }
                      >
                        <option value="absolute">Absolute</option>
                        <option value="relative">Relative</option>
                      </select>
                    </div>
                    <div>
                      <Label>Severity</Label>
                      <select
                        className={selectClass}
                        value={rule.severity}
                        onChange={(event) =>
                          updateRule(index, {
                            severity: event.target
                              .value as QualityGateRule["severity"],
                          })
                        }
                      >
                        <option value="FAIL">Fail release</option>
                        <option value="WARN">Warning</option>
                      </select>
                    </div>
                    <div className="flex items-end justify-end">
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={rules.length === 1}
                        onClick={() =>
                          setRules((current) =>
                            current.filter((_, item) => item !== index),
                          )
                        }
                      >
                        <Trash2 size={14} className="mr-1" /> Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              {createGate.error && (
                <p className="text-sm text-[var(--danger)]">
                  {createGate.error.message}
                </p>
              )}
              <Button
                disabled={
                  createGate.isPending || !activeProjectId || !rules.length
                }
                loading={createGate.isPending}
              >
                <ShieldCheck size={15} className="mr-2" /> Save quality gate
              </Button>
            </form>
          </Card>

          <Card className="overflow-hidden">
            <div className="border-b border-[var(--border)] p-5">
              <h2 className="font-semibold">Release policies</h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Run these from any completed candidate experiment.
              </p>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {gates.data?.map((gate) => (
                <article key={gate.id} className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-semibold">{gate.name}</h3>
                      {gate.description && (
                        <p className="mt-1 text-xs leading-5 text-[var(--muted)]">
                          {gate.description}
                        </p>
                      )}
                    </div>
                    <GitCompareArrows
                      size={17}
                      className="text-[var(--accent)]"
                    />
                  </div>
                  <ul className="mt-4 space-y-2">
                    {gate.rules.map((rule, index) => (
                      <li
                        key={`${gate.id}-${index}`}
                        className="text-xs text-[var(--muted)]"
                      >
                        <span
                          className={
                            rule.severity === "FAIL"
                              ? "text-[var(--danger)]"
                              : "text-[var(--warning)]"
                          }
                        >
                          {rule.severity}
                        </span>{" "}
                        · {rule.metric} · {rule.constraint.replace("_", " ")} ·{" "}
                        {formatThreshold(rule)} {rule.comparison}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
              {!gates.isLoading && !gates.data?.length && (
                <p className="p-5 text-sm text-[var(--muted)]">
                  No quality gates yet.
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
