import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/components/auth-provider";
import { SiteHeader } from "@/components/site-header";
import type { AuthSession, User } from "@/lib/types";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const makeSession = (role: User["role"]): AuthSession => ({
  user: { id: "user-1", email: "pilot@example.test", display_name: "Пилот", role, company_id: null },
  csrf_token: "csrf-test"
});

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("moderation navigation", () => {
  it("shows the queue to moderators and admins only", () => {
    act(() => {
      root.render(createElement(AuthProvider, { key: "moderator", initialSession: makeSession("moderator"), children: createElement(SiteHeader) }));
    });
    expect(container.querySelector('a[href="/moderation"]')?.textContent).toContain("Модерация");
    expect(container.querySelector('a[href="/admin"]')).toBeNull();

    act(() => {
      root.render(createElement(AuthProvider, { key: "user", initialSession: makeSession("user"), children: createElement(SiteHeader) }));
    });
    expect(container.querySelector('a[href="/moderation"]')).toBeNull();

    act(() => {
      root.render(createElement(AuthProvider, { key: "admin", initialSession: makeSession("admin"), children: createElement(SiteHeader) }));
    });
    expect(container.querySelector('a[href="/moderation"]')).not.toBeNull();
    expect(container.querySelector('a[href="/admin"]')?.textContent).toContain("Администрирование");
  });

  it.each(["moderator", "admin"] as const)("keeps %s routes available from its compact navigation", (role) => {
    act(() => {
      root.render(createElement(AuthProvider, { initialSession: makeSession(role), children: createElement(SiteHeader) }));
    });

    const header = container.querySelector("header.staff-header");
    const toggle = header?.querySelector<HTMLButtonElement>(".mobile-menu-toggle");
    expect(toggle?.getAttribute("aria-controls")).toBe("main-navigation");
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");

    act(() => toggle?.click());

    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    expect(header?.querySelector('nav a[href="/moderation"]')).not.toBeNull();
    if (role === "admin") expect(header?.querySelector('nav a[href="/admin"]')).not.toBeNull();
    else expect(header?.querySelector('nav a[href="/admin"]')).toBeNull();
  });

  it("keeps Russian dictionary copy and the current unprefixed routes", () => {
    act(() => {
      root.render(createElement(AuthProvider, { initialSession: null, children: createElement(SiteHeader) }));
    });

    expect(container.querySelector('nav[aria-label="Основная навигация"]')).not.toBeNull();
    expect(container.querySelector('nav a[href="/cars"]')?.textContent).toBe("Автомобили");
    expect(container.querySelector('nav a[href="/dealers"]')?.textContent).toBe("Компании");
    expect(container.querySelector('nav a[href="/customs-calculator"]')?.textContent).toBe("Таможенный калькулятор");
    expect(container.querySelector('nav a[href="/login"]')?.textContent).toBe("Войти");
    expect(container.querySelector('a[href="/sell"]')?.textContent).toContain("Подать объявление");
  });

  it("connects the mobile menu toggle to the navigation it controls", () => {
    act(() => {
      root.render(createElement(AuthProvider, { initialSession: null, children: createElement(SiteHeader) }));
    });

    const toggle = container.querySelector<HTMLButtonElement>(".mobile-menu-toggle");
    expect(toggle?.getAttribute("aria-controls")).toBe("main-navigation");
    expect(container.querySelector("#main-navigation")).not.toBeNull();
  });

  it("closes the open mobile menu when the primary sell link is activated", () => {
    act(() => {
      root.render(createElement(AuthProvider, { initialSession: null, children: createElement(SiteHeader) }));
    });

    const toggle = container.querySelector<HTMLButtonElement>(".mobile-menu-toggle");
    const sellLink = container.querySelector<HTMLAnchorElement>(".header-sell");
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(sellLink?.getAttribute("href")).toBe("/sell");

    act(() => toggle?.click());
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");

    sellLink?.addEventListener("click", (event) => event.preventDefault(), { once: true });
    act(() => sellLink?.click());
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
  });

  it("exposes a sign-out action inside the mobile navigation", () => {
    act(() => {
      root.render(createElement(AuthProvider, { initialSession: makeSession("user"), children: createElement(SiteHeader) }));
    });

    const signOut = container.querySelector<HTMLButtonElement>("#main-navigation .mobile-signout");
    expect(signOut?.type).toBe("button");
    expect(signOut?.textContent).toContain("Выйти");
  });
});
