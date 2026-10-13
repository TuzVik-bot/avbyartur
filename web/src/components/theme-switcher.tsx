"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { applyTheme, parseTheme, readTheme, SYSTEM_THEME_QUERY, THEME_STORAGE_KEY, type ThemePreference } from "@/lib/theme";
import styles from "./theme-switcher.module.css";

const options = [
  { value: "light", label: "Светлая", icon: Sun },
  { value: "dark", label: "Тёмная", icon: Moon },
  { value: "system", label: "Системная", icon: Monitor }
] as const;

export function ThemeSwitcher() {
  const [theme, setTheme] = useState<ThemePreference>("system");
  const [open, setOpen] = useState(false);
  const preference = useRef<ThemePreference>("system");
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    const media = window.matchMedia?.(SYSTEM_THEME_QUERY);
    function update(next: ThemePreference) {
      preference.current = next;
      setTheme(next);
      applyTheme(next, media?.matches ?? false);
    }
    update(readTheme());
    function onSystemChange() { applyTheme(preference.current, media?.matches ?? false); }
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

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    function onOutside(event: PointerEvent) {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onOutside);
    return () => document.removeEventListener("pointerdown", onOutside);
  }, [open]);

  function select(value: ThemePreference) {
    preference.current = value;
    setTheme(value);
    applyTheme(value, window.matchMedia?.(SYSTEM_THEME_QUERY).matches ?? false);
    try { localStorage.setItem(THEME_STORAGE_KEY, value); } catch { /* Selection still works when storage is blocked. */ }
    setOpen(false);
    trigger.current?.focus();
  }

  const Icon = options.find(option => option.value === theme)!.icon;
  return (
    <div ref={wrapper} className={styles.wrapper} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false); }} onKeyDown={event => {
      if (event.key === "Escape" && open) {
        event.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    }}>
      <button ref={trigger} type="button" className="icon-button" aria-label="Тема оформления" title="Тема оформления" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)} onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}><Icon size={19} aria-hidden="true" /></button>
      {open && <div ref={menu} id={id} role="menu" aria-label="Тема оформления" className={styles.menu} onKeyDown={event => {
        const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button') ?? []);
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === "ArrowDown" ? (index + 1) % items.length : event.key === "ArrowUp" ? (index + items.length - 1) % items.length : event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : null;
        if (next !== null) { event.preventDefault(); items[next]?.focus(); }
      }}>
        {options.map(({ value, label, icon: OptionIcon }) => <button key={value} type="button" role="menuitemradio" aria-checked={theme === value} tabIndex={-1} onClick={() => select(value)}>
          <OptionIcon size={20} aria-hidden="true" /><span>{label}</span>{theme === value && <Check size={19} aria-hidden="true" />}
        </button>)}
      </div>}
    </div>
  );
}
