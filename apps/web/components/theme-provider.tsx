"use client";

import { Moon, Sun } from "lucide-react";
import { createContext, useContext, useSyncExternalStore } from "react";
import { Button } from "@/components/ui";

type Theme = "light" | "dark";

const ThemeContext = createContext<{
  theme: Theme;
  setTheme: (theme: Theme) => void;
}>({ theme: "dark", setTheme: () => undefined });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(
    (onChange) => {
      window.addEventListener("agentscope-theme-change", onChange);
      return () =>
        window.removeEventListener("agentscope-theme-change", onChange);
    },
    (): Theme =>
      document.documentElement.dataset.theme === "light" ? "light" : "dark",
    (): Theme => "dark",
  );

  const setTheme = (next: Theme) => {
    document.documentElement.dataset.theme = next;
    localStorage.setItem("agentscope-theme", next);
    window.dispatchEvent(new Event("agentscope-theme-change"));
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useContext(ThemeContext);
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <Button
      type="button"
      variant="ghost"
      className={
        compact ? "group h-9 w-9 px-0" : "group w-full justify-start px-2"
      }
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={label}
      title={label}
    >
      <span
        key={theme}
        className="inline-flex animate-[theme-icon_320ms_cubic-bezier(0.22,1,0.36,1)_both]"
      >
        {isDark ? <Sun size={16} /> : <Moon size={16} />}
      </span>
      {!compact && (
        <span className="ml-2">{isDark ? "Light mode" : "Dark mode"}</span>
      )}
    </Button>
  );
}
