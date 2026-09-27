import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "handoff-theme";

/** Resolve the initial theme: stored preference first, else system preference. */
function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

/**
 * Small, compact theme toggle. Purely UI state: it sets data-theme on the
 * document root and persists the explicit choice to localStorage. No app state,
 * backend, or API is involved.
 */
function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  // Apply the theme to <html> and persist the choice.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Ignore storage failures (e.g. private mode); theme still applies.
    }
  }, [theme]);

  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={label}
      title={label}
    >
      {isDark ? (
        // Sun icon (currently dark → offer light).
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
          <circle
            cx="12"
            cy="12"
            r="4.2"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <line x1="12" y1="2.5" x2="12" y2="5" />
            <line x1="12" y1="19" x2="12" y2="21.5" />
            <line x1="2.5" y1="12" x2="5" y2="12" />
            <line x1="19" y1="12" x2="21.5" y2="12" />
            <line x1="5.1" y1="5.1" x2="6.9" y2="6.9" />
            <line x1="17.1" y1="17.1" x2="18.9" y2="18.9" />
            <line x1="5.1" y1="18.9" x2="6.9" y2="17.1" />
            <line x1="17.1" y1="6.9" x2="18.9" y2="5.1" />
          </g>
        </svg>
      ) : (
        // Moon icon (currently light → offer dark).
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
          <path
            d="M20 14.5A8 8 0 0 1 9.5 4a0.5 0.5 0 0 0-0.7-0.6A9 9 0 1 0 20.6 15.2a0.5 0.5 0 0 0-0.6-0.7z"
            fill="currentColor"
          />
        </svg>
      )}
    </button>
  );
}

/** Quiet brand bar: product name, a calm one-line tagline, and a theme toggle. */
function Header() {
  return (
    <header className="app-header">
      <h1 className="app-title">Handoff</h1>
      <p className="app-tagline">Make work executable.</p>
      <ThemeToggle />
    </header>
  );
}

export default Header;
