"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

function readCurrent(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

// Picks up the theme the pre-hydration script already applied to <html>,
// then mirrors any change to the class attribute so every useTheme()
// caller stays in sync — even ones living in unrelated subtrees.
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    // Sync the first render (hook initialized to "light" to avoid SSR mismatch).
    setTheme(readCurrent());

    // Subscribe to <html class> changes from any other useTheme instance.
    const observer = new MutationObserver(() => setTheme(readCurrent()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const toggle = useCallback(() => {
    // Only mutate the DOM + storage; React state updates flow back through
    // the MutationObserver above, keeping every instance consistent.
    const next: Theme = readCurrent() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can fail in private mode; the toggle still flips for this session
    }
  }, []);

  return [theme, toggle];
}
