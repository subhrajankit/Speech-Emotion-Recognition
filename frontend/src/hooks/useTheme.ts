/**
 * VoiceSense AI — Theme Hook
 * Supports 'dark' | 'light', persists the choice in localStorage, and falls
 * back to the OS prefers-color-scheme on first visit. Applies the theme to
 * <html data-theme="..."> synchronously during the initial state read so the
 * first paint already uses the resolved theme (no flash of the wrong theme).
 */

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';

const THEME_STORAGE_KEY = 'voicesense-theme';

function resolveInitialTheme(): Theme {
  let theme: Theme = 'dark';

  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') {
      theme = stored;
    } else if (window.matchMedia?.('(prefers-color-scheme: light)').matches) {
      theme = 'light';
    }
  } catch {
    // localStorage/matchMedia unavailable (e.g. privacy mode) — stay dark.
  }

  // Apply before first paint to avoid a theme flash.
  document.documentElement.setAttribute('data-theme', theme);
  return theme;
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(resolveInitialTheme);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Persistence is best-effort; theming still works for the session.
    }
  }, [theme]);

  return {
    theme,
    isDark: theme === 'dark',
    setTheme,
    toggleTheme,
  };
}
