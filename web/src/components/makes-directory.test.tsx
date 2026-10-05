import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MakesDirectory } from "@/components/makes-directory";
import type { CatalogItem } from "@/lib/types";

let container: HTMLDivElement;
let root: Root;

const make = (slug: string, name: string, listing_count?: number): CatalogItem => ({ id: slug, slug, name, aliases: [], listing_count });
const links = () => [...container.querySelectorAll<HTMLAnchorElement>(".makes-list a")];
const button = (label: string) => [...container.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === label);

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

describe("MakesDirectory", () => {
  it("renders nothing when the catalog is unavailable", () => {
    act(() => { root.render(createElement(MakesDirectory, { makes: [] })); });
    expect(container.innerHTML).toBe("");
  });

  it("links makes to their catalog pages and shows only non-zero counters", () => {
    act(() => { root.render(createElement(MakesDirectory, { makes: [make("audi", "Audi", 3), make("bmw", "BMW", 0), make("volvo", "Volvo")] })); });

    expect(links().map((link) => [link.textContent, link.getAttribute("href")])).toEqual([["Audi", "/cars/audi"], ["BMW", "/cars/bmw"], ["Volvo", "/cars/volvo"]]);
    expect([...container.querySelectorAll(".makes-count")].map((count) => count.textContent)).toEqual(["3"]);
  });

  it("limits the collapsed list to the most popular makes and expands with country filters", () => {
    const many = Array.from({ length: 35 }, (_, index) => make(`make-${index}`, `Make ${String(index).padStart(2, "0")}`, index));
    many.push(make("audi", "Audi", 100));
    act(() => { root.render(createElement(MakesDirectory, { makes: many })); });

    expect(links()).toHaveLength(30);
    expect(links().map((link) => link.textContent)).toContain("Audi");
    expect(links().map((link) => link.textContent)).not.toContain("Make 00");

    act(() => { button("Все марки")?.click(); });
    expect(links()).toHaveLength(36);
    act(() => { button("Германия")?.click(); });
    expect(links().map((link) => link.textContent)).toEqual(["Audi"]);
    act(() => { button("Другие")?.click(); });
    expect(links()).toHaveLength(35);
    act(() => { button("Свернуть")?.click(); });
    expect(links()).toHaveLength(30);
  });
});
