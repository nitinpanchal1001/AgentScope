"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { apiFetch, type AuthResponse } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { ThemeToggle } from "./theme-provider";
import { Button, Card, FieldError, Input, Label } from "./ui";

const schema = z.object({
  display_name: z.string().min(1).max(120).optional(),
  email: z.email(),
  password: z
    .string()
    .min(12, "Use at least 12 characters")
    .regex(/[A-Za-z]/, "Add a letter")
    .regex(/[0-9]/, "Add a number"),
});
type Values = z.infer<typeof schema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const setSession = useAuthStore((state) => state.setSession);
  const [serverError, setServerError] = useState<string | null>(null);
  const formSchema = schema.superRefine((values, context) => {
    if (mode === "register" && !values.display_name?.trim()) {
      context.addIssue({
        code: "custom",
        path: ["display_name"],
        message: "Enter your name",
      });
    }
  });
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(formSchema),
  });

  const submit = handleSubmit(async (values) => {
    setServerError(null);
    try {
      const result = await apiFetch<AuthResponse>(`/api/v1/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      setSession(result.access_token, result.user);
      router.replace("/dashboard");
    } catch (error) {
      setServerError(
        error instanceof Error ? error.message : "Unable to continue",
      );
    }
  });

  return (
    <main className="relative grid min-h-screen bg-[var(--surface)] lg:grid-cols-2">
      <div className="absolute right-5 top-5 z-10">
        <ThemeToggle compact />
      </div>
      <section className="relative hidden overflow-hidden bg-[var(--hero)] p-12 text-[var(--hero-contrast)] lg:flex lg:flex-col lg:justify-between">
        <span className="absolute -right-20 top-24 h-44 w-44 rounded-full bg-[var(--accent-secondary)] opacity-90" />
        <span className="absolute bottom-28 right-28 h-12 w-12 rounded-lg border-8 border-white/20" />
        <Link
          href="/"
          className="relative z-10 group flex items-center gap-2.5 text-lg font-black tracking-tight"
        >
          <span className="relative flex h-8 w-8 items-center justify-center rounded-md bg-white text-xs text-[var(--hero)] transition-transform duration-200 group-hover:-translate-y-0.5">
            A
            <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[var(--accent-secondary)]" />
          </span>
          AgentScope
        </Link>
        <div className="relative z-10 max-w-xl">
          <p className="mb-5 inline-flex rounded-full bg-white/12 px-3 py-1.5 text-xs font-semibold tracking-wide text-white">
            Observe · Evaluate · Improve
          </p>
          <h1 className="text-5xl font-semibold leading-[1.06] tracking-[-0.045em]">
            Know why your agent failed before your users do.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-white/70">
            Trace agent execution, compare versions, and turn AI quality into an
            engineering signal.
          </p>
        </div>
        <p className="relative z-10 text-sm text-white/60">
          Built for teams shipping reliable agents.
        </p>
      </section>
      <section className="flex items-center justify-center bg-[var(--surface)] p-6">
        <Card className="w-full max-w-md border-0 p-7 sm:p-8">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="relative flex h-7 w-7 items-center justify-center rounded-md bg-[var(--accent)] text-xs text-[var(--accent-contrast)]">
              A
              <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[var(--accent-secondary)]" />
            </span>
            <strong>AgentScope</strong>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">
            {mode === "register" ? "Create your account" : "Welcome back"}
          </h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {mode === "register"
              ? "Start with a secure workspace for your agents."
              : "Sign in to your engineering workspace."}
          </p>
          <form className="mt-7 space-y-5" onSubmit={submit}>
            {mode === "register" && (
              <div>
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  autoComplete="name"
                  {...register("display_name")}
                />
                <FieldError message={errors.display_name?.message} />
              </div>
            )}
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                {...register("email")}
              />
              <FieldError message={errors.email?.message} />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={
                  mode === "register" ? "new-password" : "current-password"
                }
                {...register("password")}
              />
              <FieldError message={errors.password?.message} />
            </div>
            {serverError && (
              <p
                role="alert"
                className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"
              >
                {serverError}
              </p>
            )}
            <Button
              className="w-full"
              disabled={isSubmitting}
              loading={isSubmitting}
            >
              {mode === "register" ? "Create account" : "Sign in"}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-[var(--muted)]">
            {mode === "register"
              ? "Already have an account?"
              : "New to AgentScope?"}{" "}
            <Link
              className="font-semibold text-[var(--accent)] hover:underline"
              href={mode === "register" ? "/login" : "/register"}
            >
              {mode === "register" ? "Sign in" : "Create account"}
            </Link>
          </p>
        </Card>
      </section>
    </main>
  );
}
