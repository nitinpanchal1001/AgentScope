"use client";

import {
  BarChart3,
  Beaker,
  BellRing,
  Boxes,
  BrainCircuit,
  Database,
  LayoutDashboard,
  LogOut,
  Menu,
  PlayCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/theme-provider";
import { PageTransition } from "@/components/page-transition";
import { Button } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

const navigation = [
  { href: "/dashboard", label: "Workspace", icon: LayoutDashboard },
  { href: "/traces", label: "Traces", icon: Boxes },
  { href: "/monitoring", label: "Monitoring", icon: BarChart3 },
  { href: "/evaluators", label: "Evaluators", icon: Beaker },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/experiments", label: "Experiments", icon: PlayCircle },
  { href: "/quality-gates", label: "Quality gates", icon: ShieldCheck },
  {
    href: "/failure-clusters",
    label: "Failure intelligence",
    icon: BrainCircuit,
  },
  { href: "/alerts", label: "Alerts", icon: BellRing },
];

const publicRoutes = new Set(["/", "/login", "/register"]);

function Brand() {
  return (
    <Link
      href="/dashboard"
      className="group flex items-center gap-2.5 text-[15px] font-bold tracking-tight"
    >
      <span className="relative flex h-7 w-7 items-center justify-center rounded-md bg-[var(--accent)] text-xs text-[var(--accent-contrast)] transition-transform duration-200 group-hover:-translate-y-0.5">
        A
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border-2 border-[var(--sidebar)] bg-[var(--accent-secondary)]" />
      </span>
      <span>AgentScope</span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const clear = useAuthStore((state) => state.clear);
  const [mobileOpen, setMobileOpen] = useState(false);

  if (publicRoutes.has(pathname)) return children;

  const logout = async () => {
    await apiFetch("/api/v1/auth/logout", { method: "POST" }).catch(
      () => undefined,
    );
    clear();
    router.replace("/login");
  };

  const nav = (
    <nav className="space-y-0.5" aria-label="Primary navigation">
      {navigation.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/dashboard"
            ? pathname === href
            : pathname.startsWith(href) ||
              (href === "/monitoring" && pathname.startsWith("/analytics"));
        return (
          <Link
            key={href}
            href={href}
            onClick={() => {
              setMobileOpen(false);
              if (!active) {
                document.documentElement.dataset.navigating = "true";
              }
            }}
            aria-current={active ? "page" : undefined}
            className={`group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-[color,background-color,transform] duration-150 active:scale-[0.985] ${
              active
                ? "bg-[var(--accent)] font-semibold text-[var(--accent-contrast)]"
                : "text-[var(--muted)] hover:bg-[var(--hover)] hover:text-[var(--foreground)]"
            }`}
          >
            <Icon
              size={17}
              strokeWidth={1.8}
              className="transition-transform duration-150 group-hover:translate-x-0.5"
            />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      <div className="route-progress" aria-hidden="true" />
      <aside className="sticky top-0 z-30 hidden h-screen flex-col border-r border-[var(--border)] bg-[var(--sidebar)] p-4 lg:flex">
        <Brand />
        <div className="mt-7 min-h-0 flex-1 overflow-y-auto">{nav}</div>
        <div className="space-y-2 border-t border-[var(--border)] pt-3">
          <ThemeToggle />
          <div className="flex items-center gap-2.5 rounded-lg bg-[var(--surface-muted)] p-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--accent-secondary-soft)] text-xs font-bold text-[var(--accent-secondary)]">
              {user?.display_name?.charAt(0).toUpperCase() ||
                user?.email?.charAt(0).toUpperCase() ||
                "U"}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">
                {user?.display_name}
              </p>
              <p className="truncate text-[11px] text-[var(--muted)]">
                {user?.email}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            className="w-full justify-start px-2"
            onClick={logout}
          >
            <LogOut size={16} className="mr-2" /> Sign out
          </Button>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[var(--border)] bg-[var(--sidebar)] px-4 lg:hidden">
          <Brand />
          <div className="flex items-center gap-1">
            <ThemeToggle compact />
            <Button
              variant="ghost"
              className="h-9 w-9 px-0"
              onClick={() => setMobileOpen((value) => !value)}
              aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X size={19} /> : <Menu size={19} />}
            </Button>
          </div>
        </header>

        {mobileOpen && (
          <div className="fixed inset-x-0 top-16 z-20 border-b border-[var(--border)] bg-[var(--sidebar)] p-4 lg:hidden">
            {nav}
            <div className="mt-3 flex items-center justify-between border-t border-[var(--border)] px-2 pt-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  {user?.display_name}
                </p>
                <p className="truncate text-xs text-[var(--muted)]">
                  {user?.email}
                </p>
              </div>
              <Button variant="ghost" onClick={logout} aria-label="Sign out">
                <LogOut size={16} />
              </Button>
            </div>
          </div>
        )}

        <div className="min-h-screen">
          <PageTransition>{children}</PageTransition>
        </div>
      </div>
    </div>
  );
}
