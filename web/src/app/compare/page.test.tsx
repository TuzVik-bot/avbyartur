import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComparePage from "./page";
import { COMPARE_STORAGE_KEY, CompareProvider } from "@/components/compare-provider";
import { getComparisonIds } from "@/lib/comparison-state";
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
  // The selection lives in a module-level store; resync it with the cleared storage.
  getComparisonIds();
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

async function renderCompare(ids: string[], fetcher?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(ids));
  const defaultFetcher = async (input: RequestInfo | URL) => {
    const requested = new URL(String(input), "http://localhost").searchParams.getAll("ids");
    const items = requested.filter((id) => id !== "missing").map((id) => listing(id, id === "hidden" ? "paused" : "active"));
    return new Response(JSON.stringify({ items }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  const fetchMock = vi.fn(fetcher || defaultFetcher);
  vi.stubGlobal("fetch", fetchMock);
  await act(async () => { root.render(<CompareProvider><ComparePage /></CompareProvider>); await new Promise((resolve) => setTimeout(resolve, 0)); });
  return fetchMock;
}

function rowCells(key: string) {
  return [...container.querySelectorAll(`tr[data-comparison-row="${key}"] td`)].map((cell) => cell.textContent);
}

describe("compare page", () => {
  it("shows the requested comparison fields and placeholders for missing data", async () => {
    const fetchMock = await renderCompare(["visible"]);
    const labels = [...container.querySelectorAll("tbody th")].map((cell) => cell.textContent);
    expect(labels).toEqual(expect.arrayContaining(["Цена в объявлении", "Пробег", "Объём двигателя", "Коробка передач", "Город и область"]));
    for (const key of ["price", "mileage", "engine_volume", "transmission", "location"]) expect(rowCells(key)).toEqual(["Не указано"]);
    expect(container.textContent).toContain("Автомобиль visible");
    expect(container.querySelector('[aria-label="Таблица сравнения автомобилей"]')?.getAttribute("tabindex")).toBe("0");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/v1/listings/compare?ids=visible");
    expect(init).toMatchObject({ method: "GET", cache: "no-store" });
  });

  it("treats inactive and missing listings as unavailable without exposing their details", async () => {
    const fetchMock = await renderCompare(["hidden", "missing"]);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/v1/listings/compare?ids=hidden&ids=missing");
    expect(container.textContent).toContain("Объявление не опубликовано.");
    expect(container.textContent).toContain("Объявление больше не доступно.");
    expect(container.textContent).not.toContain("Автомобиль hidden");
    expect(container.textContent).not.toContain("Автомобиль missing");
    expect(rowCells("vehicle")).toEqual(["Недоступно", "Недоступно"]);
  });

  it("keeps 5xx and network failures retryable instead of calling the listings removed", async () => {
    for (const failure of [() => { throw new Error("network down"); }, () => new Response("Service unavailable", { status: 503 })]) {
      act(() => root.unmount());
      root = createRoot(container);
      let calls = 0;
      const fetcher = async (input: RequestInfo | URL) => {
        calls += 1;
        if (calls === 1) return failure();
        const requested = new URL(String(input), "http://localhost").searchParams.getAll("ids");
        return new Response(JSON.stringify({ items: requested.map((id) => listing(id)) }), { status: 200, headers: { "Content-Type": "application/json" } });
      };
      const fetchMock = await renderCompare(["network", "service"], fetcher);
      expect(container.textContent).toContain("Не удалось загрузить данные");
      expect(container.textContent).not.toContain("Объявление больше не доступно");
      const retry = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Загрузить снова");
      expect(retry).toBeDefined();
      await act(async () => { retry?.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
      expect(container.textContent).toContain("Автомобиль network");
      expect(container.textContent).toContain("Автомобиль service");
      expect(fetchMock).toHaveBeenCalledTimes(2);
    }
  });

  it("shows an empty state for an empty comparison", async () => {
    const fetchMock = await renderCompare([]);
    expect(container.textContent).toContain("Пока нет объявлений для сравнения");
    expect(container.querySelector('a[href="/cars"]')?.textContent).toBe("Перейти в каталог");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
