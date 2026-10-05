"use client";

import { useEffect, useId, useSyncExternalStore } from "react";
import { Icon } from "@/components/icon";
import { getTheme, getServerTheme, setTheme, subscribeToTheme } from "@/lib/theme";

// Keep pages without a theme control (including Chat) in sync with other tabs.
export function ThemeSync() {
  useEffect(() => subscribeToTheme(() => {}), []);
  return null;
}

export function ThemeToggle() {
  const name = useId();
  const theme = useSyncExternalStore(subscribeToTheme, getTheme, getServerTheme);

  return (
    <fieldset className="zy-join theme-switch" aria-label="Color theme">
      {(["light", "dark"] as const).map((option) => (
        <label className="zy-btn zy-join-item" data-theme-option={option} key={option}>
          <input
            className="sr-only"
            type="radio"
            name={name}
            value={option}
            checked={theme === option}
            onChange={() => setTheme(option)}
            aria-label={`${option === "light" ? "Light" : "Dark"} mode`}
          />
          <Icon name={option === "light" ? "sun" : "moon"} />
          <span>{option === "light" ? "Light" : "Dark"}</span>
        </label>
      ))}
    </fieldset>
  );
}
