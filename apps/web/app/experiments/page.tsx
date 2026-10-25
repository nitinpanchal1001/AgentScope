"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FlaskConical, Play, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { type Dataset } from "@/lib/datasets";
import { type Experiment } from "@/lib/experiments";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };
type Environment = { id: string; name: string; slug: string };
type Evaluator = {
  id: string;
  name: string;
  versions: { id: string; version: number; type: string }[];
};

function statusClass(status: string) {
  if (status === "COMPLETED") return "text-[var(--success)]";
  if (status === "RUNNING") return "text-[var(--info)]";
  if (status === "FAILED") return "text-[var(--danger)]";
  if (status === "CANCELLED") return "text-[var(--warning)]";
  return "text-[var(--muted)]";
}

export default function ExperimentsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [datasetVersionId, setDatasetVersionId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [evaluatorIds, setEvaluatorIds] = useState<string[]>([]);
  const [endpoint, setEndpoint] = useState("");
  const [model, setModel] = useState("");
  const [promptVersion, setPromptVersion] = useState("");
  const [maxConcurrency, setMaxConcurrency] = useState(5);
  const [headersFromEnv, setHeadersFromEnv] = useState("{}");
  const [parameters, setParameters] = useState("{}");
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
  const datasets = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () =>
      apiFetch<Dataset[]>(`/api/v1/projects/${activeProjectId}/datasets`),
    enabled: Boolean(activeProjectId),
  });
  const evaluators = useQuery({
    queryKey: ["evaluators", activeProjectId],
    queryFn: () =>
      apiFetch<Evaluator[]>(`/api/v1/projects/${activeProjectId}/evaluators`),
    enabled: Boolean(activeProjectId),
  });
  const experiments = useQuery({
    queryKey: ["experiments", activeProjectId],
    queryFn: () =>
      apiFetch<Experiment[]>(`/api/v1/projects/${activeProjectId}/experiments`),
    enabled: Boolean(activeProjectId),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "RUNNING")
        ? 2_000
        : false,
  });
  const createExperiment = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Experiment>(`/api/v1/projects/${activeProjectId}/experiments`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (experiment) => {
      queryClient.invalidateQueries({
        queryKey: ["experiments", activeProjectId],
      });
      router.push(
        `/experiments/${experiment.id}?project_id=${activeProjectId}`,
      );
    },
  });
  const startExperiment = useMutation({
    mutationFn: (experimentId: string) =>
      apiFetch<Experiment>(
        `/api/v1/projects/${activeProjectId}/experiments/${experimentId}/start`,
        { method: "POST" },
      ),
    onSuccess: (experiment) =>
      router.push(
        `/experiments/${experiment.id}?project_id=${activeProjectId}`,
      ),
  });

  const allVersions =
    datasets.data?.flatMap((dataset) =>
      dataset.versions.map((version) => ({
        id: version.id,
        label: `${dataset.name} · v${version.version} · ${version.item_count} cases`,
      })),
    ) ?? [];
  const latestEvaluatorVersions =
    evaluators.data?.flatMap((evaluator) =>
      evaluator.versions.slice(0, 1).map((version) => ({
        id: version.id,
        label: `${evaluator.name} · v${version.version} · ${version.type}`,
      })),
    ) ?? [];
  const activeDatasetVersionId = datasetVersionId || allVersions[0]?.id || "";
  const activeEnvironmentId = environmentId || environments.data?.[0]?.id || "";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const parsedHeaders = JSON.parse(headersFromEnv) as Record<
        string,
        string
      >;
      const parsedParameters = JSON.parse(parameters) as Record<
        string,
        unknown
      >;
      createExperiment.mutate({
        name,
        dataset_version_id: activeDatasetVersionId,
        environment_id: activeEnvironmentId,
        evaluator_version_ids: evaluatorIds,
        max_concurrency: maxConcurrency,
        agent: {
          type: "http",
          endpoint,
          model: model || null,
          prompt_version: promptVersion || null,
          headers_from_env: parsedHeaders,
          parameters: parsedParameters,
        },
      });
      setFormError("");
    } catch {
      setFormError(
        "Header mappings and parameters must be valid JSON objects.",
      );
    }
  };

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading experiments" />;

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
            Evaluation / Execution
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Experiments</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Run a fixed dataset against an HTTP agent with bounded parallelism
            and immutable evaluator versions.
          </p>
        </div>

        <Card className="grid gap-4 p-5 md:grid-cols-2">
          <div>
            <Label>Organization</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={activeOrganizationId}
              onChange={(event) => {
                setOrganizationId(event.target.value);
                setProjectId("");
                setDatasetVersionId("");
                setEvaluatorIds([]);
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
                setDatasetVersionId("");
                setEvaluatorIds([]);
              }}
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
            <div className="mb-5 flex items-center gap-2">
              <Plus size={17} className="text-[var(--accent)]" />
              <h2 className="font-semibold">Configure experiment</h2>
            </div>
            <form className="space-y-4" onSubmit={submit}>
              <div>
                <Label>Name</Label>
                <Input
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Support prompt v3"
                />
              </div>
              <div>
                <Label>Dataset version</Label>
                <select
                  required
                  className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
                  value={activeDatasetVersionId}
                  onChange={(event) => setDatasetVersionId(event.target.value)}
                >
                  {allVersions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Trace environment</Label>
                <select
                  required
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
              <div>
                <Label>Agent endpoint</Label>
                <Input
                  required
                  type="url"
                  value={endpoint}
                  onChange={(event) => setEndpoint(event.target.value)}
                  placeholder="https://agent.example.com/invoke"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Model</Label>
                  <Input
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                  />
                </div>
                <div>
                  <Label>Prompt version</Label>
                  <Input
                    value={promptVersion}
                    onChange={(event) => setPromptVersion(event.target.value)}
                  />
                </div>
              </div>
              <div>
                <Label>Max concurrency</Label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={maxConcurrency}
                  onChange={(event) =>
                    setMaxConcurrency(Number(event.target.value))
                  }
                />
              </div>
              <div>
                <Label>Evaluator versions</Label>
                <div className="space-y-2 rounded-md border border-[var(--border)] p-3">
                  {latestEvaluatorVersions.map((item) => (
                    <label key={item.id} className="flex gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={evaluatorIds.includes(item.id)}
                        onChange={(event) =>
                          setEvaluatorIds((current) =>
                            event.target.checked
                              ? [...current, item.id]
                              : current.filter((id) => id !== item.id),
                          )
                        }
                      />
                      {item.label}
                    </label>
                  ))}
                  {!latestEvaluatorVersions.length && (
                    <p className="text-xs text-[var(--muted)]">
                      Create an evaluator before running an experiment.
                    </p>
                  )}
                </div>
              </div>
              <div>
                <Label>Header → worker environment variable</Label>
                <Input
                  className="font-mono text-xs"
                  value={headersFromEnv}
                  onChange={(event) => setHeadersFromEnv(event.target.value)}
                  placeholder='{"Authorization":"AGENT_AUTH_HEADER"}'
                />
              </div>
              <div>
                <Label>Model parameters</Label>
                <Input
                  className="font-mono text-xs"
                  value={parameters}
                  onChange={(event) => setParameters(event.target.value)}
                />
              </div>
              {(formError || createExperiment.error) && (
                <p className="text-sm text-[var(--danger)]">
                  {formError || createExperiment.error?.message}
                </p>
              )}
              <Button
                className="w-full"
                disabled={
                  createExperiment.isPending ||
                  !activeDatasetVersionId ||
                  !activeEnvironmentId ||
                  !evaluatorIds.length
                }
                loading={createExperiment.isPending}
              >
                Create pending experiment
              </Button>
            </form>
          </Card>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-5">
              <h2 className="font-semibold">Experiment history</h2>
              <FlaskConical size={18} className="text-[var(--accent)]" />
            </div>
            <div className="divide-y divide-[var(--border)]">
              {experiments.data?.map((experiment) => (
                <div
                  key={experiment.id}
                  className="flex items-center gap-4 p-5"
                >
                  <Link
                    href={`/experiments/${experiment.id}?project_id=${activeProjectId}`}
                    className="min-w-0 flex-1"
                  >
                    <div className="flex items-center gap-2">
                      <p className="truncate font-semibold">
                        {experiment.name}
                      </p>
                      <span
                        className={`font-mono text-[10px] ${statusClass(experiment.status)}`}
                      >
                        {experiment.status}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs text-[var(--muted)]">
                      {experiment.dataset_name} v{experiment.dataset_version} ·{" "}
                      {experiment.completed_cases}/{experiment.total_cases}{" "}
                      complete
                    </p>
                  </Link>
                  {experiment.status === "PENDING" && (
                    <Button
                      variant="outline"
                      onClick={() => startExperiment.mutate(experiment.id)}
                      disabled={startExperiment.isPending}
                      loading={startExperiment.isPending}
                    >
                      <Play size={14} className="mr-1" /> Run
                    </Button>
                  )}
                </div>
              ))}
              {!experiments.isLoading && !experiments.data?.length && (
                <p className="p-10 text-center text-sm text-[var(--muted)]">
                  No experiments in this project yet.
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
