"use client";

import { useEffect, useRef, useState } from "react";
import { applyTheme, parseTheme, readTheme, SYSTEM_THEME_QUERY, THEME_STORAGE_KEY, type ThemePreference } from "@/lib/theme";
import styles from "./theme-switcher.module.css";

export function ThemeSwitcher() {
  const [dark, setDark] = useState(false);
  const preference = useRef<ThemePreference>("system");

  useEffect(() => {
    const media = window.matchMedia?.(SYSTEM_THEME_QUERY);
    function update(next: ThemePreference) {
      preference.current = next;
      const resolvedDark = next === "system" ? media?.matches ?? false : next === "dark";
      setDark(resolvedDark);
      applyTheme(next, media?.matches ?? false);
    }
    update(readTheme());
    function onSystemChange() { update(preference.current); }
    function onStorage(event: StorageEvent) {
      if (event.key === THEME_STORAGE_KEY || event.key === null) update(parseTheme(event.newValue));
    }
    media?.addEventListener("change", onSystemChange);
    window.addEventListener("storage", onStorage);
    return () => {
      media?.removeEventListener("change", onSystemChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  function toggle() {
    const next: ThemePreference = dark ? "light" : "dark";
    preference.current = next;
    setDark(!dark);
    applyTheme(next, window.matchMedia?.(SYSTEM_THEME_QUERY).matches ?? false);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Theme still changes when storage is blocked. */ }
  }

  const action = `Цвет сайта: включить ${dark ? "светлую" : "тёмную"} тему`;
  return (
    <button type="button" className={styles.toggle} data-headlights={dark ? "on" : "off"} aria-label={action} aria-pressed={dark} title={action} onClick={toggle}>
      <svg className={styles.headlights} width="34" height="26" viewBox="0 0 40 30" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path className={styles.lamp} d="M21 6c8 0 13 4 13 9s-5 9-13 9V6Z" />
        <path d="M24 9v12" />
        <g className={styles.beams}><path d="M5 7h10M3 12h12M3 18h12M5 23h10" /></g>
      </svg>
      <span className={styles.copy}><span className={styles.label}>Цвет сайта</span><span className={styles.state}>{dark ? "Тёмный" : "Светлый"}</span></span>
    </button>
  );
}
