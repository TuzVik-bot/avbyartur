import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminCatalogItem } from "@/components/admin-catalog-item";
import { AdminRuntimeSetting } from "@/components/admin-runtime-setting";
import { adminApi, type AdminCatalogItem as CatalogItem, type RuntimeSetting } from "@/lib/admin";

const mocks = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));

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

function setValue(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

const catalogItem: CatalogItem = {
  id: "make-1", kind: "makes", name: "Марка", slug: "marka", aliases: [], parent_id: null,
  year_from: null, year_to: null, source_name: null, source: null, manual_override: false, revision: 2
};
const setting: RuntimeSetting = { key: "private_listing_quota", value: 5, revision: 2, source: "environment" };

describe("admin catalog and runtime setting edits", () => {
  it("requires the catalog confirmation phrase and includes password, reason, and expected revision", async () => {
    const update = vi.spyOn(adminApi, "updateCatalogItem").mockResolvedValue({ item: { ...catalogItem, name: "Новое имя", revision: 3 }, changed: true });
    await act(async () => root.render(createElement(AdminCatalogItem, { kind: "makes", initialItem: catalogItem })));
    await act(async () => container.querySelector<HTMLButtonElement>(".admin-catalog-actions button")!.click());
    const form = container.querySelector<HTMLFormElement>(".admin-catalog-edit")!;
    setValue(form.querySelector<HTMLInputElement>('input[name="name"]')!, "Новое имя");
    setValue(form.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!, "Исправление по подтверждённому источнику");
    setValue(form.querySelector<HTMLInputElement>('input[name="current_password"]')!, "current-password");
    setValue(form.querySelector<HTMLInputElement>('input[name="confirmation"]')!, "UPDATE_CATALOG");
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(update).toHaveBeenCalledWith("makes", "make-1", {
      name: "Новое имя", expected_revision: 2, reason: "Исправление по подтверждённому источнику",
      confirmation: "UPDATE_CATALOG", current_password: "current-password", aliases: []
    });
    expect(container.textContent).toContain("Изменение сохранено и добавлено в историю");
  });

  it("requires explicit setting confirmation and submits a versioned update", async () => {
    const update = vi.spyOn(adminApi, "updateRuntimeSetting").mockResolvedValue({ setting: { ...setting, value: 6, revision: 3, source: "override" }, changed: true });
    await act(async () => root.render(createElement(AdminRuntimeSetting, { initialSetting: setting })));
    await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
    const form = container.querySelector<HTMLFormElement>(".admin-runtime-setting-form")!;
    setValue(form.querySelector<HTMLInputElement>('input[name="value"]')!, "6");
    setValue(form.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!, "Лимит согласован для теста");
    setValue(form.querySelector<HTMLInputElement>('input[name="current_password"]')!, "current-password");
    setValue(form.querySelector<HTMLInputElement>('input[name="confirmation"]')!, "UPDATE_SETTING");
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(update).toHaveBeenCalledWith("private_listing_quota", {
      value: 6, expected_revision: 2, reason: "Лимит согласован для теста",
      confirmation: "UPDATE_SETTING", current_password: "current-password"
    });
    expect(container.textContent).toContain("Лимит сохранён и записан в аудит");
  });
});
