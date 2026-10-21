import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VinFormatCheck } from "@/components/vin-format-check";

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
  vi.restoreAllMocks();
});

function changeValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("VinFormatCheck", () => {
  it("checks only the local string format, clears the VIN, and never sends a request", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    act(() => root.render(createElement(VinFormatCheck)));

    const input = container.querySelector<HTMLInputElement>("#vin-format-input");
    const form = container.querySelector<HTMLFormElement>("form");
    expect(input).not.toBeNull();
    expect(form).not.toBeNull();
    changeValue(input!, "1HGCM82633A004352");

    act(() => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(container.querySelector('[role="status"]')?.textContent).toContain("История автомобиля не проверена");
    expect(input!.value).toBe("");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(form!.getAttribute("action")).toBeNull();
  });
});
