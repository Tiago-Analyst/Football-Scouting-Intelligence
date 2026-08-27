"use client";

import { useSyncExternalStore } from "react";

import { cn } from "@/lib/cn";

import { THEME_STORAGE_KEY } from "./ThemeScript";

type Theme = "system" | "light" | "dark";

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "☀" },
  { value: "system", label: "System", icon: "◐" },
  { value: "dark", label: "Dark", icon: "☾" },
];

/** Fired on same-tab writes; the storage event only fires in *other* tabs. */
const THEME_EVENT = "fri:theme-change";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(THEME_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(THEME_EVENT, onChange);
  };
}

function getSnapshot(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    // Private browsing can throw on access; fall back to following the OS.
    return "system";
  }
}

/** The server cannot know a visitor's stored preference. */
function getServerSnapshot(): Theme {
  return "system";
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  try {
    if (theme === "system") {
      root.removeAttribute("data-theme");
      localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      root.setAttribute("data-theme", theme);
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  } catch {
    // Storage unavailable: the attribute still applies for this page view.
  }
  window.dispatchEvent(new Event(THEME_EVENT));
}

/**
 * Three-state theme control: light, system, dark.
 *
 * localStorage is an external store, so it is read through
 * `useSyncExternalStore` rather than copied into state inside an effect. React
 * uses the server snapshot during hydration and swaps to the real value
 * afterwards, which avoids both a hydration mismatch and the cascading render
 * that a setState-in-effect would cause.
 */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-md border border-border bg-surface p-0.5"
    >
      {OPTIONS.map((option) => {
        const active = theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={option.label}
            onClick={() => apply(option.value)}
            className={cn(
              "h-6 w-6 rounded text-xs leading-none transition-colors",
              active ? "bg-surface-3 text-text" : "text-subtle hover:text-text",
            )}
          >
            <span aria-hidden>{option.icon}</span>
          </button>
        );
      })}
    </div>
  );
}
