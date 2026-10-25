import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComparePage from "./page";
import { COMPARE_STORAGE_KEY, CompareProvider } from "@/components/compare-provider";
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

async function renderCompare(ids: string[], fetcher?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(ids));
  const defaultFetcher = async (input: RequestInfo | URL) => {
    const id = String(input).split("/").at(-1);
    if (id === "missing") return new Response("", { status: 404 });
    return new Response(JSON.stringify({ listing: listing(id || "unknown", id === "hidden" ? "paused" : "active") }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  const fetchMock = vi.fn(fetcher || defaultFetcher);
  vi.stubGlobal("fetch", fetchMock);
  await act(async () => { root.render(<CompareProvider><ComparePage /></CompareProvider>); await Promise.resolve(); await Promise.resolve(); });
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
    expect([...container.querySelectorAll("tbody td")].map((cell) => cell.textContent)).toEqual(Array(8).fill("Не указано"));
    expect(container.querySelector('[aria-label="Таблица сравнения автомобилей"]')?.getAttribute("tabindex")).toBe("0");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/listings/visible", { credentials: "omit", cache: "no-store" });
  });

  it("treats inactive and missing listings as unavailable without exposing their details", async () => {
    await renderCompare(["hidden", "missing"]);
    expect(container.textContent.match(/Объявление недоступно или больше не опубликовано\./g)).toHaveLength(2);
    expect(container.textContent).not.toContain("Автомобиль hidden");
    expect(container.textContent).not.toContain("Автомобиль missing");
  });

  it("keeps 5xx and network failures retryable instead of calling the listings removed", async () => {
    let calls = 0;
    const fetcher = async (input: RequestInfo | URL) => {
      calls += 1;
      const id = String(input).split("/").at(-1) || "item";
      if (calls === 1) throw new Error("network down");
      if (calls === 2) return new Response("Service unavailable", { status: 503 });
      if (calls === 3) return new Response("not-json", { status: 200 });
      return new Response(JSON.stringify({ listing: listing(id) }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const fetchMock = await renderCompare(["network", "service", "malformed"], fetcher);
    expect(container.textContent).toContain("Не удалось проверить объявление");
    expect(container.textContent).not.toContain("Объявление недоступно или больше не опубликовано.");
    const retry = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Повторить проверку"));
    expect(retry?.textContent).toContain("Повторить проверку");
    await act(async () => { retry?.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).toContain("Автомобиль network");
    expect(container.textContent).toContain("Автомобиль service");
    expect(container.textContent).toContain("Автомобиль malformed");
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("shows an empty state for an empty comparison", async () => {
    const fetchMock = await renderCompare([]);
    expect(container.textContent).toContain("Пока нет автомобилей для сравнения");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
