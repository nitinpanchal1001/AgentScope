"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileUp,
  Fingerprint,
  Plus,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import {
  type Dataset,
  type DatasetVersion,
  type DatasetVersionPage,
  parseFlexibleValue,
  parseTools,
} from "@/lib/datasets";

const textAreaClass =
  "min-h-24 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 py-2 font-mono text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--subtle)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]";

function JsonValue({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-[var(--border)] bg-[var(--code)] p-3 text-xs leading-5 text-[var(--code-text)]">
      {value == null ? "—" : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function DatasetDetail() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project_id") ?? "";
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [versionNumber, setVersionNumber] = useState<number>();
  const [page, setPage] = useState(1);
  const [input, setInput] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const [expectedTools, setExpectedTools] = useState("");
  const [context, setContext] = useState("");
  const [importFormat, setImportFormat] = useState("jsonl");
  const [importFile, setImportFile] = useState<File>();

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setReady(true));
  }, [clear, router, token]);

  const dataset = useQuery({
    queryKey: ["dataset", projectId, params.id],
    queryFn: () =>
      apiFetch<Dataset>(`/api/v1/projects/${projectId}/datasets/${params.id}`),
    enabled: ready && Boolean(projectId),
  });
  const activeVersion =
    versionNumber ?? dataset.data?.latest_version.version ?? 1;
  const version = useQuery({
    queryKey: ["dataset-version", projectId, params.id, activeVersion, page],
    queryFn: () =>
      apiFetch<DatasetVersionPage>(
        `/api/v1/projects/${projectId}/datasets/${params.id}/versions/${activeVersion}?page=${page}&page_size=25`,
      ),
    enabled: ready && Boolean(projectId) && Boolean(dataset.data),
  });

  const refresh = (created: DatasetVersion) => {
    setVersionNumber(created.version);
    setPage(1);
    queryClient.invalidateQueries({
      queryKey: ["dataset", projectId, params.id],
    });
    queryClient.invalidateQueries({
      queryKey: ["dataset-version", projectId, params.id],
    });
  };
  const appendCase = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<DatasetVersion>(
        `/api/v1/projects/${projectId}/datasets/${params.id}/items`,
        { method: "POST", body: JSON.stringify(body) },
      ),
    onSuccess: (created) => {
      setInput("");
      setExpectedOutput("");
      setExpectedTools("");
      setContext("");
      refresh(created);
    },
  });
  const importCases = useMutation({
    mutationFn: (form: FormData) =>
      apiFetch<DatasetVersion>(
        `/api/v1/projects/${projectId}/datasets/${params.id}/versions/import`,
        { method: "POST", body: form },
      ),
    onSuccess: (created) => {
      setImportFile(undefined);
      refresh(created);
    },
  });

  const append = (event: FormEvent) => {
    event.preventDefault();
    appendCase.mutate({
      case: {
        input: parseFlexibleValue(input),
        expected_output: parseFlexibleValue(expectedOutput),
        expected_tools: parseTools(expectedTools),
        context: parseFlexibleValue(context),
        metadata: {},
      },
      metadata: { source: "manual" },
    });
  };
  const upload = (event: FormEvent) => {
    event.preventDefault();
    if (!importFile) return;
    const form = new FormData();
    form.set("format", importFormat);
    form.set("metadata", JSON.stringify({ source: "upload" }));
    form.set("file", importFile);
    importCases.mutate(form);
  };

  if (!projectId)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--danger)]">
        Open this dataset from the project dataset list.
      </div>
    );
  if (!ready || dataset.isLoading)
    return <PageLoader label="Loading dataset" />;
  if (!dataset.data || dataset.error)
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--danger)]">
        {dataset.error?.message ?? "Dataset not found"}
      </div>
    );

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div>
          <Link
            href="/datasets"
            className="mb-3 flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <ArrowLeft size={15} /> Datasets
          </Link>
          <p className="text-sm font-medium text-[var(--muted)]">
            Golden dataset / Immutable history
          </p>
          <h1 className="mt-2 text-3xl font-semibold">{dataset.data.name}</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {dataset.data.description || "No description"}
          </p>
        </div>

        <Card className="grid gap-4 p-5 md:grid-cols-[0.5fr_1fr_1fr]">
          <div>
            <Label>Version</Label>
            <select
              className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
              value={activeVersion}
              onChange={(event) => {
                setVersionNumber(Number(event.target.value));
                setPage(1);
              }}
            >
              {dataset.data.versions.map((item) => (
                <option key={item.id} value={item.version}>
                  v{item.version} · {item.item_count} cases
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Content hash</Label>
            <p className="flex h-10 items-center gap-2 overflow-hidden rounded-md border border-[var(--border)] px-3 font-mono text-xs text-[var(--muted)]">
              <Fingerprint size={14} className="shrink-0" />
              <span className="truncate">
                {version.data?.version.content_hash}
              </span>
            </p>
          </div>
          <div>
            <Label>Created</Label>
            <p className="flex h-10 items-center rounded-md border border-[var(--border)] px-3 text-sm text-[var(--muted)]">
              {version.data
                ? new Date(version.data.version.created_at).toLocaleString()
                : "—"}
            </p>
          </div>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-5">
              <div>
                <h2 className="font-semibold">Version {activeVersion} cases</h2>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Stored snapshots never change after creation.
                </p>
              </div>
              <span className="font-mono text-xs text-[var(--accent)]">
                {version.data?.pagination.total_items ?? 0} total
              </span>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {version.data?.items.map((item) => (
                <article key={item.id} className="space-y-3 p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-xs text-[var(--accent)]">
                      Case #{item.ordinal}
                    </p>
                    <p className="text-xs text-[var(--muted)]">
                      {item.expected_tools.length
                        ? item.expected_tools.join(", ")
                        : "No expected tools"}
                    </p>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div>
                      <Label>Input</Label>
                      <JsonValue value={item.input} />
                    </div>
                    <div>
                      <Label>Expected output</Label>
                      <JsonValue value={item.expected_output} />
                    </div>
                  </div>
                </article>
              ))}
              {!version.isLoading && !version.data?.items.length && (
                <p className="p-8 text-center text-sm text-[var(--muted)]">
                  No cases on this page.
                </p>
              )}
            </div>
            {version.data && version.data.pagination.total_pages > 1 && (
              <div className="flex items-center justify-between border-t border-[var(--border)] p-4">
                <Button
                  variant="outline"
                  disabled={!version.data.pagination.has_previous}
                  onClick={() => setPage((value) => value - 1)}
                >
                  <ChevronLeft size={15} className="mr-1" /> Previous
                </Button>
                <span className="text-xs text-[var(--muted)]">
                  Page {page} of {version.data.pagination.total_pages}
                </span>
                <Button
                  variant="outline"
                  disabled={!version.data.pagination.has_next}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next <ChevronRight size={15} className="ml-1" />
                </Button>
              </div>
            )}
          </Card>

          <div className="space-y-6">
            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <Plus size={17} className="text-[var(--accent)]" />
                <h2 className="font-semibold">Append a case</h2>
              </div>
              <p className="mb-4 text-xs leading-5 text-[var(--muted)]">
                Copies the latest version and adds this case as a new immutable
                version.
              </p>
              <form className="space-y-3" onSubmit={append}>
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
                  <Label>Expected output</Label>
                  <textarea
                    className={textAreaClass}
                    value={expectedOutput}
                    onChange={(event) => setExpectedOutput(event.target.value)}
                  />
                </div>
                <div>
                  <Label>Expected tools</Label>
                  <Input
                    value={expectedTools}
                    onChange={(event) => setExpectedTools(event.target.value)}
                    placeholder="search, answer"
                  />
                </div>
                <div>
                  <Label>Context</Label>
                  <textarea
                    className={textAreaClass}
                    value={context}
                    onChange={(event) => setContext(event.target.value)}
                  />
                </div>
                {appendCase.error && (
                  <p className="text-sm text-[var(--danger)]">
                    {appendCase.error.message}
                  </p>
                )}
                <Button
                  className="w-full"
                  disabled={appendCase.isPending}
                  loading={appendCase.isPending}
                >
                  Create next version
                </Button>
              </form>
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <FileUp size={17} className="text-[var(--accent)]" />
                <h2 className="font-semibold">Import a version</h2>
              </div>
              <form className="space-y-3" onSubmit={upload}>
                <div>
                  <Label>Format</Label>
                  <select
                    className="h-10 w-full rounded-md border border-[var(--border)] bg-[var(--input)] px-3 text-sm text-[var(--foreground)] outline-none focus:border-[var(--accent)]"
                    value={importFormat}
                    onChange={(event) => setImportFormat(event.target.value)}
                  >
                    <option value="jsonl">JSONL</option>
                    <option value="json">JSON</option>
                    <option value="csv">CSV</option>
                  </select>
                </div>
                <div>
                  <Label>File</Label>
                  <Input
                    required
                    type="file"
                    accept=".json,.jsonl,.csv,application/json,text/csv"
                    onChange={(event) => setImportFile(event.target.files?.[0])}
                  />
                </div>
                {importCases.error && (
                  <p className="text-sm text-[var(--danger)]">
                    {importCases.error.message}
                  </p>
                )}
                <Button
                  className="w-full"
                  variant="outline"
                  disabled={importCases.isPending || !importFile}
                  loading={importCases.isPending}
                >
                  Validate and create
                </Button>
              </form>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function DatasetDetailPage() {
  return (
    <Suspense fallback={<PageLoader label="Loading dataset" />}>
      <DatasetDetail />
    </Suspense>
  );
}
