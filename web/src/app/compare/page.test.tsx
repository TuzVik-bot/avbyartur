import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComparePage from "./page";
import { COMPARE_STORAGE_KEY } from "@/components/compare-provider";
import type { Listing } from "@/lib/types";

let root: Root;
let container: HTMLDivElement;

function listing(id: string, status: Listing["status"] = "active"): Listing {
  return {
    id, slug: id, title: `Автомобиль ${id}`, make: null, model: null, year: null, mileage_km: null,
    fuel: null, transmission: null, drive: null, body_type: null, price: null, region: null, city: null,
    cover_url: null, photo_urls: [], seller: { id: "seller", name: "Продавец", type: "private" },
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", damaged: false, parts_only: false,
    status, revision: 1, description: "", condition: null
  };
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.clearAllMocks();
  localStorage.clear();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  localStorage.clear();
  vi.restoreAllMocks();
});

async function renderCompare(ids: string[]) {
  localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(ids));
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const id = String(input).split("/").at(-1);
    return new Response(JSON.stringify({ listing: listing(id || "unknown", id === "hidden" ? "paused" : "active") }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  await act(async () => { root.render(<ComparePage />); await Promise.resolve(); await Promise.resolve(); });
  return fetchMock;
}

describe("compare page", () => {
  it("shows the requested comparison fields and placeholders for missing data", async () => {
    const fetchMock = await renderCompare(["visible"]);
    expect(container.textContent).toContain("Цена");
    expect(container.textContent).toContain("Пробег");
    expect(container.textContent).toContain("Двигатель");
    expect(container.textContent).toContain("Коробка передач");
    expect(container.textContent).toContain("Город");
    expect(container.textContent).toContain("Не указано");
    expect(container.querySelector('[aria-label="Таблица сравнения автомобилей"]')?.getAttribute("tabindex")).toBe("0");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/listings/visible", { credentials: "omit", cache: "no-store" });
  });

  it("does not show fields from non-active listings", async () => {
    await renderCompare(["hidden"]);
    expect(container.textContent).toContain("Объявление недоступно или больше не опубликовано.");
    expect(container.textContent).not.toContain("Автомобиль hidden");
  });

  it("shows an empty state for an empty comparison", async () => {
    const fetchMock = await renderCompare([]);
    expect(container.textContent).toContain("Пока нет автомобилей для сравнения");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
