"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { apiFetch, type AuthResponse } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
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
    <main className="grid min-h-screen lg:grid-cols-[1.15fr_0.85fr]">
      <section className="hidden border-r border-[var(--border)] p-12 lg:flex lg:flex-col lg:justify-between">
        <Link href="/" className="text-lg font-black tracking-tight">
          <span className="text-[var(--accent)]">●</span> AgentScope
        </Link>
        <div className="max-w-2xl">
          <p className="mb-5 font-mono text-xs uppercase tracking-[0.25em] text-[var(--accent)]">
            Observe · Evaluate · Ship
          </p>
          <h1 className="text-5xl font-semibold leading-[1.08] tracking-[-0.04em]">
            Know why your agent failed before your users do.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-[var(--muted)]">
            Trace agent execution, compare versions, and turn AI quality into an
            engineering signal.
          </p>
        </div>
        <p className="font-mono text-xs text-[#596070]">
          AGENTSCOPE / CONTROL PLANE
        </p>
      </section>
      <section className="flex items-center justify-center p-6">
        <Card className="w-full max-w-md p-7 shadow-2xl shadow-black/20">
          <div className="mb-8 lg:hidden">
            <span className="text-[var(--accent)]">●</span>{" "}
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
                className="rounded-md border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-300"
              >
                {serverError}
              </p>
            )}
            <Button className="w-full" disabled={isSubmitting}>
              {isSubmitting
                ? "Working…"
                : mode === "register"
                  ? "Create account"
                  : "Sign in"}
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
