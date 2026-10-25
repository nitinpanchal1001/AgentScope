"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, PageLoader } from "@/components/ui";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { FailureCluster, FailureRecord } from "@/lib/failures";

export default function FailureClusterDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project") ?? "";
  const router = useRouter();
  const token = useAuthStore((state) => state.accessToken);
  const clear = useAuthStore((state) => state.clear);
  const [ready, setReady] = useState(Boolean(token));

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setReady(true));
  }, [clear, router, token]);

  const cluster = useQuery({
    queryKey: ["failure-cluster", projectId, params.id],
    queryFn: () =>
      apiFetch<FailureCluster>(
        `/api/v1/projects/${projectId}/failure-clusters/${params.id}`,
      ),
    enabled: ready && Boolean(projectId),
  });
  const failures = useQuery({
    queryKey: ["failures", projectId],
    queryFn: () =>
      apiFetch<FailureRecord[]>(`/api/v1/projects/${projectId}/failures`),
    enabled: ready && Boolean(projectId),
  });
  const members = failures.data?.filter((item) =>
    cluster.data?.failure_ids.includes(item.id),
  );

  if (!ready || cluster.isLoading)
    return <PageLoader label="Loading failure cluster" />;
  if (!projectId || cluster.error)
    return (
      <div className="p-10 text-sm text-[var(--danger)]">
        The cluster could not be loaded. Return to failure intelligence and try
        again.
      </div>
    );

  return (
    <main className="min-h-screen p-5 sm:p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <Link
          href="/failure-clusters"
          className="flex items-center gap-2 text-sm text-[var(--muted)]"
        >
          <ArrowLeft size={15} /> Failure intelligence
        </Link>
        <div>
          <p className="text-sm font-medium text-[var(--muted)]">
            {cluster.data?.summary_source}
          </p>
          <h1 className="mt-2 text-3xl font-semibold">{cluster.data?.title}</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {cluster.data?.size} recurring failures ·{" "}
            {Number(cluster.data?.failure_percentage).toFixed(1)}%
          </p>
        </div>
        <Card className="grid gap-5 p-5 md:grid-cols-3">
          <div>
            <p className="text-xs uppercase text-[var(--muted)]">Pattern</p>
            <p className="mt-2 text-sm">{cluster.data?.description}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-[var(--muted)]">
              Probable cause
            </p>
            <p className="mt-2 text-sm text-[var(--warning)]">
              {cluster.data?.probable_cause}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase text-[var(--muted)]">
              Suggested action
            </p>
            <p className="mt-2 text-sm">{cluster.data?.suggested_action}</p>
          </div>
        </Card>
        <Card className="overflow-hidden">
          <div className="border-b border-[var(--border)] p-5">
            <h2 className="font-semibold">Cluster members</h2>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {members?.map((failure) => (
              <article key={failure.id} className="p-5">
                <p className="font-mono text-[10px] text-[var(--accent)]">
                  {failure.failure_type}
                </p>
                <h3 className="mt-1 font-semibold">{failure.title}</h3>
                <p className="mt-2 text-xs text-[var(--muted)]">
                  Detected {new Date(failure.detected_at).toLocaleString()}
                </p>
                <Link
                  href={`/traces/${failure.trace_id}`}
                  className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--accent)]"
                >
                  Inspect trace <ExternalLink size={11} />
                </Link>
              </article>
            ))}
          </div>
        </Card>
      </div>
    </main>
  );
}
