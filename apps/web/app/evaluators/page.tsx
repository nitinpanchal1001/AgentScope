"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Beaker, Link2, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };
type Environment = { id: string; name: string; slug: string };
type EvaluatorVersion = {
  id: string;
  version: number;
  type: string;
  configuration: Record<string, unknown>;
  threshold: string;
  provider: string | null;
  model: string | null;
  rubric: string | null;
};
type Evaluator = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  versions: EvaluatorVersion[];
};
type Binding = {
  id: string;
  environment_id: string;
  evaluator_version_id: string;
  sample_rate: string;
  threshold: string | null;
  enabled: boolean;
};

const TYPES = [
  "EXACT_MATCH",
  "CONTAINS",
  "REGEX",
  "JSON_SCHEMA",
  "LATENCY_THRESHOLD",
  "COST_THRESHOLD",
  "REQUIRED_TOOL",
  "FORBIDDEN_TOOL",
  "TOOL_ARGUMENTS",
  "CITATION_PRESENCE",
  "SEMANTIC_SIMILARITY",
  "CORRECTNESS",
  "RELEVANCE",
  "FAITHFULNESS",
  "COMPLETENESS",
  "HALLUCINATION",
  "INSTRUCTION_FOLLOWING",
  "TOOL_SELECTION",
  "CUSTOM_RUBRIC",
];
const LLM_TYPES = new Set(TYPES.slice(11));

export default function EvaluatorsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("CONTAINS");
  const [configuration, setConfiguration] = useState('{"value":"resolved"}');
  const [threshold, setThreshold] = useState("0.8");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [rubric, setRubric] = useState("");
  const [formError, setFormError] = useState("");

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
  const activeEnvironmentId = environmentId || environments.data?.[0]?.id || "";
  const evaluators = useQuery({
    queryKey: ["evaluators", activeProjectId],
    queryFn: () =>
      apiFetch<Evaluator[]>(`/api/v1/projects/${activeProjectId}/evaluators`),
    enabled: Boolean(activeProjectId),
  });
  const bindings = useQuery({
    queryKey: ["evaluation-bindings", activeProjectId],
    queryFn: () =>
      apiFetch<Binding[]>(
        `/api/v1/projects/${activeProjectId}/evaluation-bindings`,
      ),
    enabled: Boolean(activeProjectId),
  });

  const createEvaluator = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Evaluator>(`/api/v1/projects/${activeProjectId}/evaluators`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setName("");
      setFormError("");
      queryClient.invalidateQueries({
        queryKey: ["evaluators", activeProjectId],
      });
    },
  });
  const createBinding = useMutation({
    mutationFn: (evaluatorVersionId: string) =>
      apiFetch<Binding>(
        `/api/v1/projects/${activeProjectId}/evaluation-bindings`,
        {
          method: "POST",
          body: JSON.stringify({
            environment_id: activeEnvironmentId,
            evaluator_version_id: evaluatorVersionId,
            sample_rate: "1",
            filters: {},
          }),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["evaluation-bindings", activeProjectId],
      }),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const parsed = JSON.parse(configuration) as Record<string, unknown>;
      createEvaluator.mutate({
        name,
        version: {
          type,
          configuration: parsed,
          threshold,
          provider: LLM_TYPES.has(type) ? provider : undefined,
          model:
            LLM_TYPES.has(type) || type === "SEMANTIC_SIMILARITY"
              ? model
              : undefined,
          rubric: LLM_TYPES.has(type) ? rubric : undefined,
        },
      });
      setFormError("");
    } catch {
      setFormError("Configuration must be valid JSON.");
    }
  };

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading evaluators" />;

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
            Evaluation / Registry
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Evaluators</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Version evaluation logic, then bind an immutable version to live
            traces.
          </p>
        </div>

        <Card className="grid gap-4 p-5 md:grid-cols-3">
          <div>
            <Label>Organization</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
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
            <Label>Production environment</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={activeEnvironmentId}
              onChange={(event) => setEnvironmentId(event.target.value)}
            >
              {environments.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <Card className="p-5">
            <div className="mb-5 flex items-center gap-2">
              <Plus size={17} className="text-[var(--accent)]" />
              <h2 className="font-semibold">Create evaluator</h2>
            </div>
            <form className="space-y-4" onSubmit={submit}>
              <div>
                <Label>Name</Label>
                <Input
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Support resolution check"
                />
              </div>
              <div>
                <Label>Type</Label>
                <select
                  className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
                  value={type}
                  onChange={(event) => {
                    const nextType = event.target.value;
                    setType(nextType);
                    if (LLM_TYPES.has(nextType))
                      setConfiguration(
                        '{"external_fields":["input","output","expected_output","context"]}',
                      );
                    else if (nextType === "SEMANTIC_SIMILARITY")
                      setConfiguration('{"reference_output":""}');
                  }}
                >
                  {TYPES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Configuration JSON</Label>
                <textarea
                  className="min-h-28 w-full rounded-md border border-[var(--border)] bg-[var(--input)] p-3 font-mono text-xs text-[var(--foreground)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
                  value={configuration}
                  onChange={(event) => setConfiguration(event.target.value)}
                />
              </div>
              <div>
                <Label>Pass threshold (0–1)</Label>
                <Input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={threshold}
                  onChange={(event) => setThreshold(event.target.value)}
                />
              </div>
              {(LLM_TYPES.has(type) || type === "SEMANTIC_SIMILARITY") && (
                <div>
                  <Label>Model</Label>
                  <Input
                    required
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder="gpt-6.1-sol or text-embedding-3-small"
                  />
                </div>
              )}
              {LLM_TYPES.has(type) && (
                <>
                  <div>
                    <Label>Provider</Label>
                    <Input
                      required
                      value={provider}
                      onChange={(event) => setProvider(event.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Rubric</Label>
                    <textarea
                      required
                      className="min-h-28 w-full rounded-md border border-[var(--border)] bg-[var(--input)] p-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
                      value={rubric}
                      onChange={(event) => setRubric(event.target.value)}
                    />
                  </div>
                </>
              )}
              {(formError || createEvaluator.error) && (
                <p className="text-sm text-[var(--danger)]">
                  {formError || createEvaluator.error?.message}
                </p>
              )}
              <Button
                className="w-full"
                disabled={createEvaluator.isPending}
                loading={createEvaluator.isPending}
              >
                Create immutable v1
              </Button>
            </form>
          </Card>

          <div className="space-y-4">
            {evaluators.data?.map((evaluator) => {
              const latest = evaluator.versions[0];
              const binding = bindings.data?.find(
                (item) =>
                  item.evaluator_version_id === latest?.id &&
                  item.environment_id === activeEnvironmentId,
              );
              return (
                <Card key={evaluator.id} className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <Beaker size={16} className="text-[var(--accent)]" />
                        <h2 className="font-semibold">{evaluator.name}</h2>
                      </div>
                      <p className="mt-2 text-sm text-[var(--muted)]">
                        {evaluator.description ?? "No description"}
                      </p>
                    </div>
                    <span className="rounded-full border border-[var(--border)] px-2 py-1 text-xs text-[var(--muted)]">
                      {evaluator.enabled ? "ACTIVE" : "DISABLED"}
                    </span>
                  </div>
                  {latest && (
                    <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="font-mono text-xs text-[var(--accent)]">
                            v{latest.version} · {latest.type}
                          </p>
                          <p className="mt-1 text-xs text-[var(--muted)]">
                            Threshold {latest.threshold} ·{" "}
                            {evaluator.versions.length} immutable version
                            {evaluator.versions.length === 1 ? "" : "s"}
                          </p>
                        </div>
                        {binding ? (
                          <span className="flex items-center gap-2 text-xs text-[var(--success)]">
                            <Link2 size={14} /> Bound at{" "}
                            {Number(binding.sample_rate) * 100}%
                          </span>
                        ) : (
                          <Button
                            variant="outline"
                            disabled={
                              !activeEnvironmentId || createBinding.isPending
                            }
                            loading={createBinding.isPending}
                            onClick={() => createBinding.mutate(latest.id)}
                          >
                            Bind latest
                          </Button>
                        )}
                      </div>
                      <pre className="mt-3 overflow-auto text-xs text-[var(--code-text)]">
                        {JSON.stringify(latest.configuration, null, 2)}
                      </pre>
                    </div>
                  )}
                </Card>
              );
            })}
            {!evaluators.isLoading && !evaluators.data?.length && (
              <Card className="p-10 text-center text-sm text-[var(--muted)]">
                Create the first evaluator for this project.
              </Card>
            )}
            {(evaluators.error || bindings.error || createBinding.error) && (
              <p className="text-sm text-[var(--danger)]">
                {evaluators.error?.message ||
                  bindings.error?.message ||
                  createBinding.error?.message}
              </p>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
