import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SavedSearchAction } from "@/components/saved-search-action";
import { ApiClientError, apiRequest } from "@/lib/api";
import type { ListingSearch } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  user: null as { id: string } | null,
  push: vi.fn()
}));

vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiRequest: vi.fn() };
});

const request = vi.mocked(apiRequest);
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  mocks.user = { id: "user-1" };
  mocks.push.mockReset();
  request.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function render(search: ListingSearch, title = "Audi A4") {
  await act(async () => { root.render(createElement(SavedSearchAction, { search, title })); });
}

async function openSaveForm() {
  await act(async () => { container.querySelector<HTMLButtonElement>('button[aria-label="Сохранить поиск"]')?.click(); });
}

describe("SavedSearchAction", () => {
  it("creates a canonical search without enabling notifications", async () => {
    request.mockResolvedValueOnce({ saved_search: { id: "saved-1", revision: 1 } });
    const search: ListingSearch = { q: "Audi A4", equipment: ["heated_seats", "abs"], page: "2", sort: "newest" };
    await render(search);
    await openSaveForm();
    expect(container.querySelectorAll('input[name="saved-search-name"]')).toHaveLength(1);

    await act(async () => { container.querySelector<HTMLButtonElement>(".saved-search-form button[type=submit]")?.click(); });

    const [path, options] = request.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(options.body));
    expect(path).toBe("me/saved-searches");
    expect(new Headers(options.headers).get("Idempotency-Key")).toBeTruthy();
    expect(body.url).toBe("/cars?equipment=abs&equipment=heated_seats&q=Audi+A4&sort=newest");
    expect(body.filters).toEqual({ equipment: ["abs", "heated_seats"], q: "Audi A4", sort: "newest" });
    expect(body.notifications_enabled).toBe(false);
    expect(body.notification_channel).toBeNull();
    expect(body.notification_frequency).toBe("daily");
    expect(container.textContent).toContain("Поиск сохранён без уведомлений");
  });

  it("keeps the selected listing category in saved search URLs", async () => {
    request.mockResolvedValueOnce({ saved_search: { id: "saved-trucks", revision: 1 } });
    await render({ category_code: "trucks", q: "MAN", details: "payload_kg:10000", page: "2" }, "Грузовики MAN");
    await openSaveForm();

    await act(async () => { container.querySelector<HTMLButtonElement>(".saved-search-form button[type=submit]")?.click(); });

    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.url).toBe("/trucks?category_code=trucks&details=payload_kg%3A10000&q=MAN");
    expect(body.filters).toEqual({ category_code: "trucks", details: "payload_kg:10000", q: "MAN" });
  });

  it("requires a separate explicit opt-in for daily web notifications", async () => {
    request
      .mockResolvedValueOnce({ saved_search: { id: "saved-1", revision: 1 } })
      .mockResolvedValueOnce({ saved_search: { id: "saved-1", revision: 2 } });
    await render({ q: "Audi" });
    await openSaveForm();

    await act(async () => { container.querySelector<HTMLButtonElement>('button[aria-label="Подписаться на новые объявления"]')?.click(); });

    const createBody = JSON.parse(String(request.mock.calls[0][1]?.body));
    const [path, options] = request.mock.calls[1] as [string, RequestInit];
    expect(createBody.notifications_enabled).toBe(false);
    expect(createBody.notification_channel).toBeNull();
    expect(path).toBe("me/saved-searches/saved-1");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(String(options.body))).toEqual({
      notifications_enabled: true,
      notification_channel: "web",
      notification_frequency: "daily",
      expected_revision: 1
    });
    expect(container.textContent).toContain("Подписка включена");
  });

  it("routes signed-out save choices back to the canonical current search", async () => {
    mocks.user = null;
    await render({ q: "Audi", equipment: ["rear_camera", "abs"], page: "3" });

    const links = [...container.querySelectorAll<HTMLAnchorElement>("a.button")];
    expect(links.map((link) => link.textContent?.trim())).toEqual([
      "Сохранить поиск",
      "Подписаться на новые объявления"
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/login?next=%2Fcars%3Fequipment%3Dabs%26equipment%3Drear_camera%26q%3DAudi",
      "/login?next=%2Fcars%3Fequipment%3Dabs%26equipment%3Drear_camera%26q%3DAudi"
    ]);
    expect(container.querySelector("input[name=saved-search-name]")).toBeNull();
  });

  it("reports when the search was saved but the separate subscription failed", async () => {
    request
      .mockResolvedValueOnce({ saved_search: { id: "saved-1", revision: 1 } })
      .mockRejectedValueOnce(new ApiClientError(503, { message: "Сервис уведомлений недоступен" }));
    await render({ q: "Audi" });
    await openSaveForm();

    await act(async () => { container.querySelector<HTMLButtonElement>('button[aria-label="Подписаться на новые объявления"]')?.click(); });

    expect(container.textContent).toContain("Поиск сохранён без уведомлений");
    expect(container.textContent).toContain("Поиск сохранён, но подписку включить не удалось");
  });

  it("redirects an expired session to login with the current search", async () => {
    request.mockRejectedValueOnce(new ApiClientError(401, { message: "Требуется вход" }));
    await render({ q: "Audi", sort: "newest" });
    await openSaveForm();

    await act(async () => { container.querySelector<HTMLButtonElement>(".saved-search-form button[type=submit]")?.click(); });

    expect(mocks.push).toHaveBeenCalledWith("/login?next=%2Fcars%3Fq%3DAudi%26sort%3Dnewest");
  });
});
