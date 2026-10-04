import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ManagedContentEditor } from "@/components/managed-content-editor";
import { contentApi } from "@/lib/content";

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div"); document.body.append(container);
  act(() => { root = createRoot(container); });
});
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); });

function value(name: string, text: string) {
  const element = container.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${name}"]`)!;
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set?.call(element, text);
  element.dispatchEvent(new Event("input", { bubbles: true })); element.dispatchEvent(new Event("change", { bubbles: true }));
}

it("requires step-up confirmation and saves an explicit structured template revision", async () => {
  const save = vi.spyOn(contentApi, "save").mockResolvedValue({ content: {
    id: "content-1", kind: "notification_template", key: "saved_search_email", payload: {}, status: "draft", revision: 1, updated_at: "2026-10-01T10:00:00Z"
  } });
  act(() => root.render(createElement(ManagedContentEditor, { initialItems: [], initialError: false })));
  const form = container.querySelector("form")!;
  await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  expect(save).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("пароль");
  await act(async () => {
    value("subject", "Новый автомобиль: {listing_title}"); value("body", "Поиск {search_name}\n{listing_url}");
    value("reason", "Редакция для пилота"); value("current_password", "step-up-test-password");
    container.querySelector<HTMLInputElement>('[name="confirmation"]')!.click();
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(save).toHaveBeenCalledWith("notification_template", "saved_search_email", expect.objectContaining({
    expected_revision: 0, confirmation: "UPDATE_CONTENT", status: "draft",
    payload: { subject: "Новый автомобиль: {listing_title}", body: "Поиск {search_name}\n{listing_url}" }
  }));
  expect(container.querySelector('[name="current_password"]')).toHaveProperty("value", "");
});

it("shows retryable loading failure and preserves edits after stale revision error", async () => {
  vi.spyOn(contentApi, "save").mockRejectedValue(new Error("Материал изменён; обновите редактор"));
  act(() => root.render(createElement(ManagedContentEditor, { initialItems: [], initialError: true })));
  expect(container.textContent).toContain("загрузить");
  await act(async () => {
    value("subject", "Подборка"); value("body", "Сохранённый текст"); value("reason", "Причина"); value("current_password", "test-password");
    container.querySelector<HTMLInputElement>('[name="confirmation"]')!.click();
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("изменён");
  expect(container.querySelector('[name="body"]')).toHaveProperty("value", "Сохранённый текст");
});
