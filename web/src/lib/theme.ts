export type ThemePreference = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "avtorinok-theme";
export const SYSTEM_THEME_QUERY = "(prefers-color-scheme: dark)";

export function parseTheme(value: string | null): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export function readTheme(): ThemePreference {
  try { return parseTheme(localStorage.getItem(THEME_STORAGE_KEY)); }
  catch { return "system"; }
}

export function applyTheme(preference: ThemePreference, systemDark: boolean) {
  document.documentElement.dataset.theme = preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

// Runs before the first paint; only validated, fixed values reach the DOM.
export const THEME_INIT_SCRIPT = `(function(){var t="system";try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");if(s==="light"||s==="dark")t=s}catch(e){}document.documentElement.dataset.theme=t==="system"?(window.matchMedia("${SYSTEM_THEME_QUERY}").matches?"dark":"light"):t})()`;
