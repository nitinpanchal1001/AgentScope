"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Boxes,
  ChevronRight,
  KeyRound,
  LogOut,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { apiFetch, refreshSession } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { Button, Card, FieldError, Input, Label } from "@/components/ui";

type Organization = { id: string; name: string; slug: string; role: string };
type Project = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
};
type Environment = { id: string; name: string; slug: string };
type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  environment_id: string;
  revoked_at: string | null;
  key?: string;
};

const orgSchema = z.object({
  name: z.string().min(2).max(120),
});
const projectSchema = z.object({
  name: z.string().min(2).max(120),
  description: z.string().max(2000).optional(),
});
const keySchema = z.object({
  name: z.string().min(2).max(100),
  environment_id: z.string().uuid(),
});

function WorkspaceForms({
  selectedOrg,
  selectedProject,
  onSelectProject,
}: {
  selectedOrg?: Organization;
  selectedProject?: Project;
  onSelectProject: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const orgForm = useForm<z.infer<typeof orgSchema>>({
    resolver: zodResolver(orgSchema),
  });
  const projectForm = useForm<z.infer<typeof projectSchema>>({
    resolver: zodResolver(projectSchema),
  });
  const keyForm = useForm<z.infer<typeof keySchema>>({
    resolver: zodResolver(keySchema),
  });

  const projects = useQuery({
    queryKey: ["projects", selectedOrg?.id],
    queryFn: () =>
      apiFetch<Project[]>(`/api/v1/organizations/${selectedOrg!.id}/projects`),
    enabled: Boolean(selectedOrg),
  });
  const environments = useQuery({
    queryKey: ["environments", selectedProject?.id],
    queryFn: () =>
      apiFetch<Environment[]>(
        `/api/v1/projects/${selectedProject!.id}/environments`,
      ),
    enabled: Boolean(selectedProject),
  });
  const keys = useQuery({
    queryKey: ["api-keys", selectedProject?.id],
    queryFn: () =>
      apiFetch<ApiKey[]>(`/api/v1/projects/${selectedProject!.id}/api-keys`),
    enabled:
      Boolean(selectedProject) &&
      ["OWNER", "ADMIN"].includes(selectedOrg?.role ?? ""),
  });

  useEffect(() => {
    if (!selectedProject && projects.data?.[0])
      onSelectProject(projects.data[0].id);
  }, [onSelectProject, projects.data, selectedProject]);
  useEffect(() => {
    if (environments.data?.[0] && !keyForm.getValues("environment_id"))
      keyForm.setValue("environment_id", environments.data[0].id);
  }, [environments.data, keyForm]);

  const createOrg = useMutation({
    mutationFn: (values: z.infer<typeof orgSchema>) =>
      apiFetch<Organization>("/api/v1/organizations", {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: () => {
      orgForm.reset();
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
  const createProject = useMutation({
    mutationFn: (values: z.infer<typeof projectSchema>) =>
      apiFetch<Project>(`/api/v1/organizations/${selectedOrg!.id}/projects`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: (project) => {
      projectForm.reset();
      onSelectProject(project.id);
      queryClient.invalidateQueries({
        queryKey: ["projects", selectedOrg?.id],
      });
    },
  });
  const createKey = useMutation({
    mutationFn: (values: z.infer<typeof keySchema>) =>
      apiFetch<ApiKey>(`/api/v1/projects/${selectedProject!.id}/api-keys`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: (key) => {
      setRevealedKey(key.key ?? null);
      keyForm.reset({ environment_id: key.environment_id, name: "" });
      queryClient.invalidateQueries({
        queryKey: ["api-keys", selectedProject?.id],
      });
    },
  });

  if (!selectedOrg)
    return (
      <Card className="mx-auto mt-20 max-w-xl p-8">
        <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-400/10 text-[var(--accent)]">
          <Boxes size={21} />
        </div>
        <h2 className="text-xl font-semibold">
          Create your first organization
        </h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          Organizations are the top-level security boundary. Projects,
          credentials, and telemetry never cross it.
        </p>
        <form
          className="mt-7 space-y-4"
          onSubmit={orgForm.handleSubmit((v) => createOrg.mutate(v))}
        >
          <div>
            <Label>Name</Label>
            <Input placeholder="Acme AI" {...orgForm.register("name")} />
            <FieldError message={orgForm.formState.errors.name?.message} />
          </div>
          {createOrg.error && (
            <p className="text-sm text-[var(--danger)] sm:col-span-2">
              {createOrg.error.message}
            </p>
          )}
          <Button className="w-full" disabled={createOrg.isPending}>
            Create organization
          </Button>
        </form>
      </Card>
    );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--accent)]">
            Foundation / Workspace
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            {selectedOrg.name}
          </h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Tenant role: {selectedOrg.role}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--muted)]">
          <ShieldCheck size={15} className="text-[var(--accent)]" /> Tenant
          isolation active
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-[0.75fr_1.25fr]">
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Projects</h2>
              <p className="text-xs text-[var(--muted)]">
                Scoped agent workspaces
              </p>
            </div>
            <Plus size={18} className="text-[var(--accent)]" />
          </div>
          <div className="space-y-2">
            {projects.data?.map((project) => (
              <button
                key={project.id}
                onClick={() => onSelectProject(project.id)}
                className={`flex w-full items-center justify-between rounded-lg border p-3 text-left ${project.id === selectedProject?.id ? "border-emerald-400/50 bg-emerald-400/5" : "border-[var(--border)] hover:bg-white/[0.03]"}`}
              >
                <span>
                  <span className="block text-sm font-semibold">
                    {project.name}
                  </span>
                </span>
                <ChevronRight size={16} />
              </button>
            ))}
            {!projects.isLoading && !projects.data?.length && (
              <p className="rounded-lg border border-dashed border-[var(--border)] p-4 text-sm text-[var(--muted)]">
                No projects yet.
              </p>
            )}
          </div>
          {["OWNER", "ADMIN"].includes(selectedOrg.role) && (
            <form
              className="mt-5 space-y-3 border-t border-[var(--border)] pt-5"
              onSubmit={projectForm.handleSubmit((v) =>
                createProject.mutate(v),
              )}
            >
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
                New project
              </p>
              <Input
                placeholder="Support agent"
                {...projectForm.register("name")}
              />
              <FieldError
                message={projectForm.formState.errors.name?.message}
              />
              <Button
                className="w-full"
                variant="outline"
                disabled={createProject.isPending}
              >
                Create project
              </Button>
            </form>
          )}
        </Card>
        <Card className="overflow-hidden">
          <div className="border-b border-[var(--border)] p-5">
            <h2 className="font-semibold">Project credentials</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Keys authenticate SDK telemetry and are never stored in plaintext.
            </p>
          </div>
          {!selectedProject ? (
            <div className="p-8 text-sm text-[var(--muted)]">
              Create or select a project to manage environments and API keys.
            </div>
          ) : (
            <div className="p-5">
              <div className="mb-5 flex flex-wrap gap-2">
                {environments.data?.map((env) => (
                  <span
                    key={env.id}
                    className="rounded-full border border-[var(--border)] px-3 py-1 font-mono text-xs text-[var(--muted)]"
                  >
                    {env.slug}
                  </span>
                ))}
              </div>
              {revealedKey && (
                <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-400/[0.06] p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-amber-300">
                    Copy now — shown once
                  </p>
                  <code className="mt-2 block overflow-x-auto text-sm text-amber-100">
                    {revealedKey}
                  </code>
                  <Button
                    variant="outline"
                    className="mt-3 h-8"
                    onClick={() => navigator.clipboard.writeText(revealedKey)}
                  >
                    Copy key
                  </Button>
                </div>
              )}
              {["OWNER", "ADMIN"].includes(selectedOrg.role) && (
                <form
                  className="mb-6 grid gap-3 sm:grid-cols-[1fr_1fr_auto]"
                  onSubmit={keyForm.handleSubmit((v) => createKey.mutate(v))}
                >
                  <div>
                    <Label>Key name</Label>
                    <Input
                      placeholder="Local SDK"
                      {...keyForm.register("name")}
                    />
                  </div>
                  <div>
                    <Label>Environment</Label>
                    <select
                      className="h-10 w-full rounded-md border border-[var(--border)] bg-[#0c0f15] px-3 text-sm"
                      {...keyForm.register("environment_id")}
                    >
                      {environments.data?.map((env) => (
                        <option key={env.id} value={env.id}>
                          {env.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button className="self-end" disabled={createKey.isPending}>
                    <KeyRound size={15} className="mr-2" />
                    Issue key
                  </Button>
                </form>
              )}
              <div className="divide-y divide-[var(--border)] border-y border-[var(--border)]">
                {keys.data?.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between py-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{key.name}</p>
                      <code className="text-xs text-[var(--muted)]">
                        {key.prefix}••••••••
                      </code>
                    </div>
                    <span
                      className={`text-xs ${key.revoked_at ? "text-[var(--danger)]" : "text-[var(--accent)]"}`}
                    >
                      {key.revoked_at ? "Revoked" : "Active"}
                    </span>
                  </div>
                ))}
                {!keys.data?.length && (
                  <p className="py-5 text-sm text-[var(--muted)]">
                    No API keys have been issued.
                  </p>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const token = useAuthStore((state) => state.accessToken);
  const user = useAuthStore((state) => state.user);
  const clear = useAuthStore((state) => state.clear);
  const [bootstrapped, setBootstrapped] = useState(Boolean(token));
  const [selectedOrgId, setSelectedOrgId] = useState<string>();
  const [selectedProjectId, setSelectedProjectId] = useState<string>();

  useEffect(() => {
    if (!token)
      refreshSession()
        .catch(() => {
          clear();
          router.replace("/login");
        })
        .finally(() => setBootstrapped(true));
  }, [clear, router, token]);
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiFetch<Organization[]>("/api/v1/organizations"),
    enabled: bootstrapped && Boolean(useAuthStore.getState().accessToken),
  });
  const activeOrgId = selectedOrgId ?? organizations.data?.[0]?.id;
  const selectedOrg = organizations.data?.find((org) => org.id === activeOrgId);
  const projectList = useQuery({
    queryKey: ["projects", activeOrgId],
    queryFn: () =>
      apiFetch<Project[]>(`/api/v1/organizations/${activeOrgId}/projects`),
    enabled: Boolean(activeOrgId),
  });
  const selectedProject =
    projectList.data?.find((project) => project.id === selectedProjectId) ??
    projectList.data?.[0];

  const logout = async () => {
    await apiFetch("/api/v1/auth/logout", { method: "POST" }).catch(
      () => undefined,
    );
    clear();
    router.replace("/login");
  };
  if (!bootstrapped || organizations.isLoading)
    return (
      <div className="flex min-h-screen items-center justify-center font-mono text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
        Loading control plane…
      </div>
    );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
      <aside className="border-b border-[var(--border)] bg-[#0b0e14] p-5 lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between lg:block">
          <div className="text-lg font-black">
            <span className="text-[var(--accent)]">●</span> AgentScope
          </div>
          <Button className="lg:hidden" variant="ghost" onClick={logout}>
            <LogOut size={16} />
          </Button>
        </div>
        {organizations.data && organizations.data.length > 0 && (
          <select
            aria-label="Organization"
            className="mt-5 h-10 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm"
            value={activeOrgId}
            onChange={(event) => {
              setSelectedOrgId(event.target.value);
              setSelectedProjectId(undefined);
            }}
          >
            {organizations.data.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.name}
              </option>
            ))}
          </select>
        )}
        <nav className="mt-8 hidden space-y-1 lg:block">
          <div className="flex items-center gap-3 rounded-md bg-emerald-400/10 px-3 py-2 text-sm font-semibold text-[var(--accent)]">
            <Activity size={16} /> Foundation
          </div>
          <Link
            href="/traces"
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-[var(--muted)] hover:bg-white/5 hover:text-white"
          >
            <Boxes size={16} /> Traces
          </Link>
        </nav>
        <div className="mt-8 hidden border-t border-[var(--border)] pt-5 lg:block">
          <p className="truncate text-sm font-medium">{user?.display_name}</p>
          <p className="truncate text-xs text-[var(--muted)]">{user?.email}</p>
          <Button
            variant="ghost"
            className="mt-3 w-full justify-start px-2"
            onClick={logout}
          >
            <LogOut size={15} className="mr-2" /> Sign out
          </Button>
        </div>
      </aside>
      <main className="p-5 sm:p-8 lg:p-10">
        <div className="mx-auto max-w-6xl">
          <WorkspaceForms
            selectedOrg={selectedOrg}
            selectedProject={selectedProject}
            onSelectProject={setSelectedProjectId}
          />
        </div>
      </main>
    </div>
  );
}
