import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogRequestQueue } from "@/app/admin/catalog-requests/catalog-request-queue";
import { ApiClientError } from "@/lib/api";
import { catalogRequestsApi, type CatalogRequest, type CatalogRequestMatch } from "@/lib/catalog-requests";

let container: HTMLDivElement;
let root: Root;

function request(overrides: Partial<CatalogRequest> = {}): CatalogRequest {
  return {
    id: "request-1",
    listing_id: "listing-1",
    listing_revision: 4,
    status: "pending",
    revision: 1,
    snapshot: {
      catalog: {
        make: { id: "make-1", name: "Тестовая марка" },
        model: { id: "model-1", name: "Тестовая модель" },
        generation: { id: "generation-1", name: "Поколение 1", year_from: 2000, year_to: null },
        body_type: null,
        body_variant: { id: "body-1", name: "Седан" },
      },
      manual_identity: { make: null, model: null },
      manual_parameters: {
        year: 2005,
        mileage_km: 125000,
        engine_volume_l: "2.0",
        power_hp: 150,
        fuel: "petrol",
        transmission: "automatic",
        drive: "front",
      },
    },
    manual_modification_name: "2.0 TDI quattro",
    note: "Код двигателя указан на табличке.",
    resolved_modification: null,
    review_reason: null,
    created_at: "2026-10-01T12:00:00Z",
    reviewed_at: null,
    ...overrides,
  };
}

const match: CatalogRequestMatch = {
  id: "sensitive-catalog-uuid",
  slug: "2-0-tdi",
  name: "2.0 TDI quattro",
  make: { id: "make-1", name: "Тестовая марка" },
  model: { id: "model-1", name: "Тестовая модель" },
  generation: { id: "generation-1", name: "Поколение 1", year_from: 2000, year_to: null },
  source: null,
  specs: {
    engine_code: "EA189",
    frame_code: null,
    engine_l: 2,
    power_hp: 150,
    fuel: "дизель",
    transmission: "АКПП",
    drive: "полный привод",
    production_period_raw: "2005 - 2010",
    summary_raw: null,
  },
};

function setValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  act(() => {
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    setter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function clickButton(text: string) {
  const button = [...container.querySelectorAll<HTMLButtonElement>("button")]
    .find((item) => item.textContent?.includes(text));
  if (!button) throw new Error("Missing button: " + text);
  await act(async () => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function settle() {
  await act(async () => { await Promise.resolve(); });
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  vi.spyOn(catalogRequestsApi, "listModeration").mockResolvedValue({
    items: [request()],
    total: 1,
    page: 1,
    page_size: 25,
  });
  vi.spyOn(catalogRequestsApi, "searchMatches").mockResolvedValue({ items: [match] });
  vi.spyOn(catalogRequestsApi, "review").mockResolvedValue({
    request: request({
      status: "resolved",
      revision: 2,
      resolved_modification: match,
      review_reason: "Подтверждено по характеристикам.",
    }),
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function renderQueue() {
  await act(async () => { root.render(createElement(CatalogRequestQueue)); });
  await settle();
}

describe("catalog request moderation queue", () => {
  it("returns to a populated previous page after reviewing the last pending item", async () => {
    vi.mocked(catalogRequestsApi.listModeration)
      .mockResolvedValueOnce({ items: [request({ id: "first-page" })], total: 26, page: 1, page_size: 25 })
      .mockResolvedValueOnce({ items: [request()], total: 26, page: 2, page_size: 25 })
      .mockResolvedValueOnce({ items: [request({ id: "first-page" })], total: 25, page: 1, page_size: 25 });
    await renderQueue();
    await clickButton("Вперёд");
    const reason = container.querySelector<HTMLTextAreaElement>('textarea');
    if (!reason) throw new Error("Missing review reason");
    setValue(reason, "Не найден подтверждённый вариант");
    await clickButton("Отклонить");
    await settle();
    expect(catalogRequestsApi.listModeration).toHaveBeenLastCalledWith({ status: "pending", page: 1, page_size: 25 });
    expect(container.textContent).not.toContain("Страница 2 из 1");
    expect(container.textContent).toContain("Тестовая модель");
  });

  it("lets a moderator search and link a named existing catalog match with a reason", async () => {
    await renderQueue();
    expect(container.textContent).toContain("Тестовая модель");
    expect(container.textContent).not.toContain("EA189");

    const query = container.querySelector<HTMLInputElement>('input[aria-label="Название или характеристика"]');
    if (!query) throw new Error("Missing catalog search field");
    setValue(query, "EA189");
    await clickButton("Найти совпадение");
    expect(catalogRequestsApi.searchMatches).toHaveBeenCalledWith("request-1", "EA189");
    expect(container.textContent).toContain("Поколение 1");
    expect(container.textContent).toContain("Код двигателя");
    expect(container.textContent).toContain("EA189");

    await clickButton("2.0 TDI quattro");
    const reason = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Причина решения"]');
    if (!reason) throw new Error("Missing review reason field");
    setValue(reason, "Подтверждено по характеристикам.");
    await clickButton("Связать существующую модификацию");

    expect(catalogRequestsApi.review).toHaveBeenCalledWith("request-1", {
      expected_revision: 1,
      decision: "resolve",
      reason: "Подтверждено по характеристикам.",
      resolved_modification_id: match.id,
    });
    expect(container.textContent).not.toContain(match.id);
    expect(container.textContent).not.toContain("Создать модификацию");
  });

  it("requires a review reason and explains stale revisions with a refresh path", async () => {
    vi.mocked(catalogRequestsApi.review).mockRejectedValueOnce(
      new ApiClientError(409, { code: "revision_conflict", message: "Catalog request changed" }),
    );
    await renderQueue();
    const query = container.querySelector<HTMLInputElement>('input[aria-label="Название или характеристика"]');
    if (!query) throw new Error("Missing catalog search field");
    setValue(query, "2.0 TDI quattro");
    await clickButton("Найти совпадение");
    await clickButton("2.0 TDI quattro");
    const reason = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Причина решения"]');
    if (!reason) throw new Error("Missing review reason field");
    const resolve = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent?.includes("Связать существующую модификацию"));
    expect(resolve?.disabled).toBe(true);
    expect(catalogRequestsApi.review).not.toHaveBeenCalled();

    setValue(reason, "Повторное сопоставление подтверждено.");
    await clickButton("Связать существующую модификацию");
    expect(container.querySelector('[role="alert"]')?.textContent?.toLowerCase()).toContain("обновите очередь");
  });

  it("offers retry after queue loading fails", async () => {
    vi.mocked(catalogRequestsApi.listModeration)
      .mockRejectedValueOnce(new Error("API unavailable"))
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 25 });
    await renderQueue();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Не удалось загрузить очередь");
    await clickButton("Повторить");
    expect(catalogRequestsApi.listModeration).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("Запросов пока нет");
  });
});
