import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeSwitcher } from "./theme-switcher";
import { THEME_INIT_SCRIPT, THEME_STORAGE_KEY } from "@/lib/theme";

let root: Root;
let container: HTMLDivElement;
let systemDark: boolean;
let listeners: Set<() => void>;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  systemDark = false;
  listeners = new Set();
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    get matches() { return systemDark; },
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener)
  })));
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

function render() { act(() => root.render(<ThemeSwitcher />)); }
function trigger() { return container.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!; }
function choose(label: string) {
  act(() => trigger().click());
  const option = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')).find(button => button.textContent === label)!;
  act(() => option.click());
}
function changeSystem(dark: boolean) {
  systemDark = dark;
  act(() => listeners.forEach(listener => listener()));
}

describe("theme preference", () => {
  it("follows system changes by default and after switching back from a fixed theme", () => {
    render();
    expect(document.documentElement.dataset.theme).toBe("light");
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    choose("Светлая");
    changeSystem(false);
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("light");
    choose("Системная");
    expect(document.documentElement.dataset.theme).toBe("dark");
    changeSystem(false);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("persists dark selection, restores it on remount and synchronizes tabs", () => {
    render();
    choose("Тёмная");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    act(() => root.unmount());
    root = createRoot(container);
    render();
    expect(document.documentElement.dataset.theme).toBe("dark");
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "light" })));
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: null })));
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("supports keyboard focus, arrows, Escape and outside dismissal", () => {
    render();
    act(() => trigger().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    expect(document.activeElement?.textContent).toBe("Системная");
    act(() => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    expect(document.activeElement?.textContent).toBe("Светлая");
    act(() => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(container.querySelector('[role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(trigger());
    act(() => trigger().click());
    act(() => document.body.dispatchEvent(new Event("pointerdown", { bubbles: true })));
    expect(container.querySelector('[role="menu"]')).toBeNull();
  });

  it("works when browser storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
    render();
    choose("Тёмная");
    expect(document.documentElement.dataset.theme).toBe("dark");
    choose("Системная");
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("applies persisted theme before hydration and rejects unknown values", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    window.eval(THEME_INIT_SCRIPT);
    expect(document.documentElement.dataset.theme).toBe("dark");
    localStorage.setItem(THEME_STORAGE_KEY, "unknown");
    window.eval(THEME_INIT_SCRIPT);
    expect(document.documentElement.dataset.theme).toBe("light");
    systemDark = true;
    window.eval(THEME_INIT_SCRIPT);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
