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
  vi.restoreAllMocks();
});

function render() { act(() => root.render(<ThemeSwitcher />)); }
function trigger() { return container.querySelector<HTMLButtonElement>('button[aria-pressed]')!; }
function toggle() { act(() => trigger().click()); }
function changeSystem(dark: boolean) {
  systemDark = dark;
  act(() => listeners.forEach(listener => listener()));
}

describe("theme preference", () => {
  it("aims the light rays upward in light theme and downward in dark theme", () => {
    render();
    function verticalDirections() {
      const path = container.querySelector('svg g path')?.getAttribute('d') ?? "";
      return [...path.matchAll(/M(\d+) (\d+)L(\d+) (\d+)/g)].map(match => Number(match[4]) - Number(match[2]));
    }
    expect(verticalDirections()).toHaveLength(4);
    expect(verticalDirections().every(delta => delta < 0)).toBe(true);
    toggle();
    expect(verticalDirections()).toHaveLength(4);
    expect(verticalDirections().every(delta => delta > 0)).toBe(true);
  });
  it("follows system theme until the user clicks the headlights", () => {
    render();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(trigger().dataset.headlights).toBe("off");
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(trigger().dataset.headlights).toBe("on");
    toggle();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(trigger().getAttribute("aria-pressed")).toBe("false");
    expect(trigger().getAttribute("aria-label")).toContain("включить тёмную тему");
    changeSystem(false);
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("light");
    toggle();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(trigger().getAttribute("aria-pressed")).toBe("true");
    expect(trigger().getAttribute("aria-label")).toContain("включить светлую тему");
  });

  it("persists dark selection, restores it on remount and synchronizes tabs", () => {
    render();
    toggle();
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

  it("works when browser storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
    render();
    toggle();
    expect(document.documentElement.dataset.theme).toBe("dark");
    toggle();
    expect(document.documentElement.dataset.theme).toBe("light");
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
