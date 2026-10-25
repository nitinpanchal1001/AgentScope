"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Database, FileJson, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { type Dataset, parseFlexibleValue, parseTools } from "@/lib/datasets";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };

const textAreaClass =
  "min-h-24 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 py-2 font-mono text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--subtle)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]";

export default function DatasetsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [input, setInput] = useState('{"message":"Where is my order?"}');
  const [expectedOutput, setExpectedOutput] = useState("");
  const [expectedTools, setExpectedTools] = useState("");
  const [context, setContext] = useState("");

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
  const datasets = useQuery({
    queryKey: ["datasets", activeProjectId],
    queryFn: () =>
      apiFetch<Dataset[]>(`/api/v1/projects/${activeProjectId}/datasets`),
    enabled: Boolean(activeProjectId),
  });
  const createDataset = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Dataset>(`/api/v1/projects/${activeProjectId}/datasets`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (dataset) => {
      setName("");
      setDescription("");
      queryClient.invalidateQueries({
        queryKey: ["datasets", activeProjectId],
      });
      router.push(`/datasets/${dataset.id}?project_id=${activeProjectId}`);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    createDataset.mutate({
      name,
      description: description || null,
      metadata: { source: "manual" },
      items: [
        {
          input: parseFlexibleValue(input),
          expected_output: parseFlexibleValue(expectedOutput),
          expected_tools: parseTools(expectedTools),
          context: parseFlexibleValue(context),
          metadata: {},
        },
      ],
    });
  };

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading datasets" />;

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
            Evaluation / Golden data
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Datasets</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Build reproducible test sets. Every change creates a content-hashed,
            immutable version.
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
            <div className="mb-5 flex items-center gap-2">
              <Plus size={17} className="text-[var(--accent)]" />
              <h2 className="font-semibold">Create with first case</h2>
            </div>
            <form className="space-y-4" onSubmit={submit}>
              <div>
                <Label>Name</Label>
                <Input
                  required
                  maxLength={160}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Customer support golden set"
                />
              </div>
              <div>
                <Label>Description</Label>
                <Input
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Critical regression cases"
                />
              </div>
              <div>
                <Label>Input (JSON or text)</Label>
                <textarea
                  required
                  className={textAreaClass}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                />
              </div>
              <div>
                <Label>Expected output (JSON or text)</Label>
                <textarea
                  className={textAreaClass}
                  value={expectedOutput}
                  onChange={(event) => setExpectedOutput(event.target.value)}
                />
              </div>
              <div>
                <Label>Expected tools (comma-separated)</Label>
                <Input
                  value={expectedTools}
                  onChange={(event) => setExpectedTools(event.target.value)}
                  placeholder="lookup_order, send_reply"
                />
              </div>
              <div>
                <Label>Context (JSON or text)</Label>
                <textarea
                  className={textAreaClass}
                  value={context}
                  onChange={(event) => setContext(event.target.value)}
                />
              </div>
              {createDataset.error && (
                <p className="text-sm text-[var(--danger)]">
                  {createDataset.error.message}
                </p>
              )}
              <Button
                className="w-full"
                disabled={createDataset.isPending || !activeProjectId}
                loading={createDataset.isPending}
              >
                Create immutable v1
              </Button>
            </form>
          </Card>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-5">
              <div>
                <h2 className="font-semibold">Golden datasets</h2>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Select one to inspect versions and import cases.
                </p>
              </div>
              <Database size={18} className="text-[var(--accent)]" />
            </div>
            <div className="divide-y divide-[var(--border)]">
              {datasets.data?.map((dataset) => (
                <Link
                  key={dataset.id}
                  href={`/datasets/${dataset.id}?project_id=${activeProjectId}`}
                  className="flex items-center justify-between gap-4 p-5 transition-colors hover:bg-[var(--hover)]"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{dataset.name}</p>
                    <p className="mt-1 truncate text-xs text-[var(--muted)]">
                      {dataset.description || "No description"}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-mono text-xs text-[var(--accent)]">
                      v{dataset.latest_version.version}
                    </p>
                    <p className="mt-1 text-xs text-[var(--muted)]">
                      {dataset.latest_version.item_count} cases
                    </p>
                  </div>
                </Link>
              ))}
              {!datasets.isLoading && !datasets.data?.length && (
                <div className="p-10 text-center text-sm text-[var(--muted)]">
                  <FileJson className="mx-auto mb-3" size={24} />
                  No datasets in this project yet.
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
