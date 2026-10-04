import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchSort } from "@/components/search-sort";

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

describe("search sorting", () => {
  it("keeps active filters, carries currency, and submits the chosen sort", async () => {
    await act(async () => root.render(createElement(SearchSort, {
      search: { q: "BMW 3", make_id: "make-1", city_id: "city-1", page: "3", currency: "USD", sort: "newest" }
    })));

    const form = container.querySelector<HTMLFormElement>("form")!;
    const requestSubmit = vi.spyOn(form, "requestSubmit").mockImplementation(() => undefined);
    const select = container.querySelector<HTMLSelectElement>('select[name="sort"]')!;
    expect(new FormData(form).get("q")).toBe("BMW 3");
    expect(new FormData(form).get("city_id")).toBe("city-1");
    expect(new FormData(form).get("page")).toBeNull();
    expect(new FormData(form).get("currency")).toBe("USD");

    select.value = "price_asc";
    await act(async () => { select.dispatchEvent(new Event("change", { bubbles: true })); });

    expect(requestSubmit).toHaveBeenCalledOnce();
    expect(new FormData(form).get("sort")).toBe("price_asc");
  });

  it("disables price sorting when no fresh exchange rate is available", async () => {
    await act(async () => root.render(createElement(SearchSort, {
      search: {},
      priceOperationsAvailable: false
    })));

    expect(container.querySelector<HTMLSelectElement>('option[value="price_asc"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLSelectElement>('option[value="price_desc"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLSelectElement>('option[value="year_desc"]')?.disabled).toBe(false);
  });
});
