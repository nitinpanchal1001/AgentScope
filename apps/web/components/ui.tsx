import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold transition-[color,background-color,border-color,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] active:scale-[0.98] disabled:pointer-events-none disabled:opacity-55",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--accent)] text-[var(--accent-contrast)] hover:bg-[var(--accent-strong)]",
        outline:
          "border border-[var(--border-strong)] bg-transparent text-[var(--foreground)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]",
        danger: "bg-[var(--danger)] text-white hover:brightness-105",
        ghost:
          "bg-transparent text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--foreground)]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    loading?: boolean;
  };

export function Button({
  className,
  variant,
  asChild,
  loading = false,
  children,
  disabled,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={cn(buttonVariants({ variant }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Spinner className="mr-2" size="sm" />}
      {children}
    </Component>
  );
}

export const controlClassName =
  "w-full rounded-md border border-[var(--border)] bg-[var(--input)] text-[var(--foreground)] outline-none transition-[border-color,box-shadow,background-color] placeholder:text-[var(--subtle)] hover:border-[var(--border-strong)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] disabled:cursor-not-allowed disabled:opacity-60";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(controlClassName, "h-10 px-3 text-sm", className)}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(controlClassName, "h-10 px-3 text-sm", className)}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(controlClassName, "min-h-24 px-3 py-2 text-sm", className)}
      {...props}
    />
  );
}

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "mb-1.5 block text-xs font-medium text-[var(--muted)]",
        className,
      )}
      {...props}
    />
  );
}

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-[var(--border)] bg-[var(--surface)]",
        className,
      )}
      {...props}
    />
  );
}

export function Spinner({
  className,
  size = "md",
}: {
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const sizes = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-8 w-8" };
  return (
    <span
      aria-hidden="true"
      className={cn("relative inline-flex shrink-0", sizes[size], className)}
    >
      <span className="absolute inset-0 animate-[loader-orbit_900ms_linear_infinite] rounded-full border-[1.5px] border-current border-r-transparent border-t-transparent opacity-90" />
      <span className="absolute inset-[22%] animate-[loader-orbit_650ms_linear_infinite_reverse] rounded-full border border-current border-b-transparent opacity-45" />
    </span>
  );
}

export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex min-h-[65vh] items-center justify-center p-8"
      role="status"
      aria-live="polite"
    >
      <div className="flex animate-[loader-arrive_300ms_ease-out_both] flex-col items-center gap-3 text-[var(--muted)]">
        <div className="relative rounded-lg border border-[var(--accent-border)] bg-[var(--accent-soft)] p-3">
          <Spinner size="lg" className="relative text-[var(--accent)]" />
        </div>
        <span className="text-sm font-medium">{label}</span>
      </div>
    </div>
  );
}

export function FieldError({ message }: { message?: string }) {
  return message ? (
    <p className="mt-1.5 text-xs text-[var(--danger)]" role="alert">
      {message}
    </p>
  ) : null;
}
