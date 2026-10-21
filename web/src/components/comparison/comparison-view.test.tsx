import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ComparisonView } from "@/components/comparison/comparison-view";
import * as comparisonApi from "@/lib/comparison-api";
import { addComparisonId, clearComparisonIds } from "@/lib/comparison-state";
import type { Listing } from "@/lib/types";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  clearComparisonIds();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  clearComparisonIds();
  vi.restoreAllMocks();
});

function listing(id: string, overrides: Partial<Listing> = {}): Listing {
  return {
    id,
    slug: id,
    title: `Марка Модель ${id}`,
    make: { id: "make-1", slug: "marka", name: "Марка" },
    model: { id: "model-1", slug: "model", name: "Модель" },
    year: 2020,
    mileage_km: 50000,
    fuel: "petrol",
    transmission: "manual",
    drive: "front",
    price: { amount: "10000", currency: "BYN" },
    region: { id: "region-1", slug: "region", name: "Область" },
    city: { id: "city-1", slug: "minsk", name: "Минск" },
    seller: { id: "seller-1", type: "private", name: "Продавец" },
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    damaged: false,
    parts_only: false,
    status: "active",
    revision: 1,
    description: "Описание",
    condition: "used",
    photo_urls: [],
    ...overrides
  };
}

describe("comparison view", () => {
  it("loads current public data and labels sold and unavailable listings honestly", async () => {
    addComparisonId("one");
    addComparisonId("two");
    addComparisonId("gone");
    vi.spyOn(comparisonApi, "fetchComparisonListings").mockResolvedValue({ items: [
      listing("one", {
        status: "active",
        price: { amount: "10000", currency: "USD", display_byn: "32000", rate_date: "2026-10-18" }
      }),
      listing("two", {
        status: "sold",
        price: { amount: "32000", currency: "BYN" }
      })
    ] });

    await act(async () => {
      root.render(<ComparisonView />);
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Продано");
    expect(container.textContent).toContain("Объявление больше не доступно");
    expect(container.querySelector('a[href="/cars/marka/model/one"]')?.textContent).toContain("Открыть объявление");
    expect(container.querySelector('[data-comparison-row="price"]')?.getAttribute("data-differences")).toBe("false");
    expect(container.textContent).toContain("10 000 USD");
    expect(container.textContent).toContain("≈ 32 000 BYN по курсу на 18.10.2026");
    expect(container.textContent).toContain("Валюта цены отличается");
    expect(container.textContent).toContain("не подтверждает техническое состояние");
    expect(comparisonApi.fetchComparisonListings).toHaveBeenCalledWith(["one", "two", "gone"]);
  });

  it("does not expose details returned for an owner's unpublished listing", async () => {
    addComparisonId("private");
    vi.spyOn(comparisonApi, "fetchComparisonListings").mockResolvedValue({
      items: [listing("private", { title: "Черновик из личного кабинета", status: "paused" })]
    });

    await act(async () => {
      root.render(<ComparisonView />);
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Объявление не опубликовано");
    expect(container.textContent).not.toContain("Черновик из личного кабинета");
  });

  it("explains the empty selection and points back to the public catalog", async () => {
    await act(async () => root.render(<ComparisonView />));
    expect(container.textContent).toContain("Пока нет объявлений для сравнения");
    expect(container.querySelector('a[href="/cars"]')?.textContent).toContain("Перейти в каталог");
  });
});
