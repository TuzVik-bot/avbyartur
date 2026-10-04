import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SavedSearches, type SavedSearch } from "@/components/saved-searches";
import { apiRequest } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiRequest: vi.fn() };
});

const request = vi.mocked(apiRequest);
const search = (overrides: Partial<SavedSearch> = {}): SavedSearch => ({
  id: "search-1",
  name: "Кроссоверы в Минске",
  url: "/cars?body_type=suv&city_id=minsk",
  filters: { body_type: "suv", city_id: "minsk" },
  status: "active",
  revision: 2,
  notifications_enabled: false,
  notification_channel: null,
  notification_frequency: "daily",
  created_at: "2026-09-30T10:00:00Z",
  updated_at: "2026-09-30T10:00:00Z",
  ...overrides
});

let container: HTMLDivElement;
let root: Root;

function setInputValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  request.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("saved searches", () => {
  it("renders an empty state and creates a search from a relative URL", async () => {
    const created = search({ id: "search-2", name: "Мой новый поиск", url: "/cars?q=Belgee", filters: { q: "Belgee" } });
    request.mockResolvedValueOnce({ saved_search: created });
    await act(async () => root.render(createElement(SavedSearches, { initialItems: [], initialUrl: "/cars?q=Belgee" })));

    expect(container.textContent).toContain("Сохранённых поисков пока нет");
    const form = container.querySelector<HTMLFormElement>("form")!;
    const name = container.querySelector<HTMLInputElement>('input[name="name"]')!;
    await act(async () => { setInputValue(name, "Мой новый поиск"); });
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });

    expect(request).toHaveBeenCalledWith("me/saved-searches", expect.objectContaining({ method: "POST", body: expect.stringContaining('"url":"/cars?q=Belgee"') }));
    expect(container.textContent).toContain("Мой новый поиск");
    expect(container.textContent).toContain("Поиск сохранён");
  });

  it("saves notification preferences and pauses a search", async () => {
    const updated = search({ revision: 3, notifications_enabled: true, notification_channel: "email", notification_frequency: "weekly" });
    const paused = search({ revision: 4, status: "paused", notifications_enabled: true, notification_channel: "email", notification_frequency: "weekly" });
    request.mockResolvedValueOnce({ saved_search: updated }).mockResolvedValueOnce({ saved_search: paused });
    await act(async () => root.render(createElement(SavedSearches, { initialItems: [search()] })));

    expect(container.textContent).toContain("Email — пока не отправляется");
    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => { checkbox.click(); });
    const selects = container.querySelectorAll<HTMLSelectElement>("select");
    selects[0].value = "email";
    await act(async () => { selects[0].dispatchEvent(new Event("change", { bubbles: true })); });
    selects[1].value = "weekly";
    await act(async () => { selects[1].dispatchEvent(new Event("change", { bubbles: true })); });
    const save = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Сохранить уведомления"))!;
    await act(async () => { save.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

    expect(request).toHaveBeenCalledWith("me/saved-searches/search-1", expect.objectContaining({ method: "PATCH", body: expect.stringContaining('"notifications_enabled":true') }));
    const pause = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Пауза"))!;
    await act(async () => { pause.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(request).toHaveBeenCalledWith("me/saved-searches/search-1/pause", expect.objectContaining({ method: "POST" }));
    expect(container.textContent).toContain("На паузе");
  });

  it("rejects external URLs before making a request", async () => {
    await act(async () => root.render(createElement(SavedSearches, { initialItems: [], initialUrl: "https://example.com" })));
    const name = container.querySelector<HTMLInputElement>('input[name="name"]')!;
    await act(async () => { setInputValue(name, "Внешний"); });
    const url = container.querySelector<HTMLInputElement>('input[name="url"]')!;
    await act(async () => { setInputValue(url, "https://example.com/cars"); });
    const form = container.querySelector<HTMLFormElement>("form")!;
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });

    expect(request).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("только поиск на этом сайте");
  });
});
