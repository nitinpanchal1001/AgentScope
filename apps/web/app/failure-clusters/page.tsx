"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  ExternalLink,
  RefreshCw,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, Input, Label, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import {
  type FailureCluster,
  type FailureRecord,
  type SimilarFailure,
} from "@/lib/failures";

type Organization = { id: string; name: string };
type Project = { id: string; name: string };

export default function FailureClustersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SimilarFailure[]>([]);

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
  const failures = useQuery({
    queryKey: ["failures", activeProjectId],
    queryFn: () =>
      apiFetch<FailureRecord[]>(`/api/v1/projects/${activeProjectId}/failures`),
    enabled: Boolean(activeProjectId),
  });
  const clusters = useQuery({
    queryKey: ["failure-clusters", activeProjectId],
    queryFn: () =>
      apiFetch<FailureCluster[]>(
        `/api/v1/projects/${activeProjectId}/failure-clusters`,
      ),
    enabled: Boolean(activeProjectId),
  });
  const rebuild = useMutation({
    mutationFn: () =>
      apiFetch<FailureCluster[]>(
        `/api/v1/projects/${activeProjectId}/failure-clusters/rebuild`,
        { method: "POST" },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["failure-clusters", activeProjectId],
      }),
  });
  const search = useMutation({
    mutationFn: () =>
      apiFetch<SimilarFailure[]>(
        `/api/v1/projects/${activeProjectId}/failures/search`,
        {
          method: "POST",
          body: JSON.stringify({ query, limit: 20 }),
        },
      ),
    onSuccess: setSearchResults,
  });
  const visibleFailures = searchResults.length
    ? searchResults.map((item) => ({
        ...item.failure,
        similarity: item.similarity,
      }))
    : (failures.data?.map((item) => ({ ...item, similarity: null })) ?? []);

  if (!ready || organizations.isLoading)
    return <PageLoader label="Loading failure intelligence" />;
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
            Failure intelligence
          </p>
          <h1 className="mt-2 text-3xl font-semibold">
            Recurring failure clusters
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Search bounded failure documents semantically and inspect
            density-derived patterns.
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
        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-5">
              <div>
                <h2 className="font-semibold">Clusters</h2>
                <p className="text-xs text-[var(--muted)]">
                  Probable causes are explicitly inferred.
                </p>
              </div>
              <Button
                variant="outline"
                onClick={() => rebuild.mutate()}
                disabled={rebuild.isPending}
                loading={rebuild.isPending}
              >
                <RefreshCw size={14} className="mr-2" /> Rebuild
              </Button>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {clusters.data?.map((cluster) => (
                <article key={cluster.id} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">{cluster.title}</h3>
                      <p className="mt-1 text-xs text-[var(--muted)]">
                        {cluster.size} failures ·{" "}
                        {Number(cluster.failure_percentage).toFixed(1)}%
                      </p>
                    </div>
                    <BrainCircuit size={17} className="text-[var(--accent)]" />
                  </div>
                  <p className="mt-3 text-sm text-[var(--muted)]">
                    {cluster.description}
                  </p>
                  <p className="mt-2 text-xs text-[var(--warning)]">
                    {cluster.probable_cause}
                  </p>
                  <p className="mt-2 text-xs">{cluster.suggested_action}</p>
                  <Link
                    href={`/failure-clusters/${cluster.id}?project=${activeProjectId}`}
                    className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--accent)]"
                  >
                    Inspect cluster <ExternalLink size={11} />
                  </Link>
                </article>
              ))}
              {!clusters.isLoading && !clusters.data?.length && (
                <p className="p-5 text-sm text-[var(--muted)]">
                  No recurring clusters. At least two similar failures are
                  required.
                </p>
              )}
            </div>
          </Card>
          <Card className="overflow-hidden">
            <div className="border-b border-[var(--border)] p-5">
              <div className="flex gap-2">
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Describe a failure…"
                />
                <Button
                  onClick={() => search.mutate()}
                  disabled={!query}
                  loading={search.isPending}
                  aria-label="Search failures"
                >
                  <Search size={15} />
                </Button>
              </div>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {visibleFailures.map((failure) => (
                <article key={failure.id} className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-mono text-[10px] text-[var(--accent)]">
                        {failure.failure_type}
                      </p>
                      <h3 className="mt-1 font-semibold">{failure.title}</h3>
                    </div>
                    {failure.similarity != null && (
                      <span className="text-xs text-[var(--muted)]">
                        {failure.similarity.toFixed(3)}
                      </span>
                    )}
                  </div>
                  <Link
                    href={`/traces/${failure.trace_id}`}
                    className="mt-3 flex items-center gap-1 text-xs text-[var(--accent)]"
                  >
                    Inspect trace <ExternalLink size={11} />
                  </Link>
                </article>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
