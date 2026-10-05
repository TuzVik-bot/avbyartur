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

function selectValue(name: string, text: string) {
  const element = container.querySelector<HTMLSelectElement>(`[name="${name}"]`)!;
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set?.call(element, text);
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function chooseContentKind(kind: string) {
  const element = container.querySelector<HTMLSelectElement>(".admin-filter-form select")!;
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set?.call(element, kind);
  element.dispatchEvent(new Event("change", { bubbles: true }));
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

it("saves a structured article draft with its topic, publication date and verified HTTPS sources", async () => {
  const save = vi.spyOn(contentApi, "save").mockResolvedValue({ content: {
    id: "article-1", kind: "article", key: "inspection-before-buying", payload: {}, status: "draft", revision: 1, updated_at: "2026-10-04T10:00:00Z"
  } });
  act(() => root.render(createElement(ManagedContentEditor, { initialItems: [], initialError: false })));
  act(() => chooseContentKind("article"));
  expect(container.querySelector('[name="content_key"]')).not.toBeNull();
  if (!container.querySelector('[name="content_key"]')) return;
  await act(async () => {
    value("content_key", "inspection-before-buying");
    value("title", "Как осмотреть транспорт перед покупкой");
    value("summary", "Порядок проверки документов и состояния транспорта перед сделкой.");
    selectValue("topic", "inspection");
    value("published_at", "2026-10-04");
    value("sources", "Официальный источник | https://example.gov.by/checklist");
    value("body", "Проверьте документы и сопоставьте идентификаторы. Осмотрите кузов и агрегаты перед оформлением сделки.");
    value("reason", "Черновик для проверки владельцем"); value("current_password", "step-up-test-password");
    container.querySelector<HTMLInputElement>('[name="confirmation"]')!.click();
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(save).toHaveBeenCalledWith("article", "inspection-before-buying", expect.objectContaining({
    expected_revision: 0, status: "draft", confirmation: "UPDATE_CONTENT",
    payload: expect.objectContaining({
      slug: "inspection-before-buying", topic: "inspection", published_at: "2026-10-04",
      sources: [{ title: "Официальный источник", url: "https://example.gov.by/checklist" }]
    })
  }));
});

it("does not publish an article until its publication date is entered", async () => {
  const save = vi.spyOn(contentApi, "save");
  act(() => root.render(createElement(ManagedContentEditor, { initialItems: [], initialError: false })));
  act(() => chooseContentKind("article"));
  expect(container.querySelector('[name="content_key"]')).not.toBeNull();
  if (!container.querySelector('[name="content_key"]')) return;
  await act(async () => {
    value("content_key", "inspection-before-buying");
    value("title", "Как осмотреть транспорт перед покупкой");
    value("summary", "Порядок проверки документов и состояния транспорта перед сделкой.");
    selectValue("topic", "inspection");
    value("body", "Проверьте документы и сопоставьте идентификаторы. Осмотрите кузов и агрегаты перед оформлением сделки.");
    selectValue("status", "published");
    value("reason", "Публикация материала"); value("current_password", "step-up-test-password");
    container.querySelector<HTMLInputElement>('[name="confirmation"]')!.click();
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(save).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("дату публикации");
});

it("keeps an existing article slug stable while allowing its content to be edited", () => {
  act(() => root.render(createElement(ManagedContentEditor, { initialError: false, initialItems: [{
    id: "article-1", kind: "article", key: "inspection-before-buying", status: "draft", revision: 1,
    updated_at: "2026-10-04T10:00:00Z",
    payload: { slug: "inspection-before-buying", title: "Осмотр", summary: "Проверка перед покупкой транспорта.", topic: "inspection",
      body: "Проверьте документы и идентификаторы до сделки. Осмотрите состояние транспортного средства.", published_at: null, sources: [] }
  }] })));
  act(() => chooseContentKind("article"));
  act(() => value("content_key", "inspection-before-buying"));
  expect(container.querySelector<HTMLInputElement>('[name="content_key"]')?.disabled).toBe(true);
  expect(container.querySelector<HTMLInputElement>('[name="title"]')?.disabled).not.toBe(true);
});

const article = (key: string) => ({ id: key, key, kind: "article" as const, status: "draft" as const, revision: 3,
  updated_at: "2026-10-05T00:00:00Z", payload: { slug: key, title: `Материал ${key}`, summary: "Проверка перед покупкой транспорта.",
    topic: "inspection", body: `Документы и идентификаторы транспорта проверяются до сделки: ${key}`, published_at: null, sources: [] } });

it("selects existing articles explicitly and starts a blank new draft", () => {
  act(() => root.render(createElement(ManagedContentEditor, { initialError: false, initialItems: [article("first"), article("second")] })));
  act(() => chooseContentKind("article"));
  expect(container.querySelector('[name="existing_article"]')).not.toBeNull();
  act(() => selectValue("existing_article", "first"));
  expect(container.querySelector('[name="title"]')).toHaveProperty("value", "Материал first");
  expect(container.querySelector('[name="content_key"]')).toHaveProperty("disabled", true);
  act(() => selectValue("existing_article", "second"));
  expect(container.querySelector('[name="body"]')).toHaveProperty("value", expect.stringContaining("second"));
  act(() => Array.from(container.querySelectorAll("button")).find(item => item.textContent?.includes("Новая статья"))!.click());
  expect(container.querySelector('[name="content_key"]')).toHaveProperty("value", "");
  expect(container.querySelector('[name="content_key"]')).toHaveProperty("disabled", false);
  expect(container.querySelector('[name="title"]')).toHaveProperty("value", "");
  expect(container.querySelector('[name="status"]')).toHaveProperty("value", "draft");
});

it("refreshes all admin pages so an article after the first page can be edited", async () => {
  const firstPage = Array.from({ length: 100 }, (_, index) => article(`article-${index}`));
  const later = article("later-page");
  const list = vi.spyOn(contentApi, "list").mockResolvedValueOnce({ items: firstPage, total: 101, page: 1, page_size: 100 })
    .mockResolvedValueOnce({ items: [later], total: 101, page: 2, page_size: 100 });
  const save = vi.spyOn(contentApi, "save").mockResolvedValue({ content: { ...later, revision: 4 } });
  act(() => root.render(createElement(ManagedContentEditor, { initialError: false, initialItems: firstPage })));
  act(() => chooseContentKind("article"));
  await act(async () => Array.from(container.querySelectorAll("button")).find(item => item.textContent?.includes("Обновить"))!.click());
  expect(list).toHaveBeenCalledTimes(2);
  act(() => selectValue("existing_article", "later-page"));
  expect(container.querySelector('[name="title"]')).toHaveProperty("value", "Материал later-page");
  await act(async () => {
    value("title", "Исправленный материал"); value("reason", "Обновление"); value("current_password", "test-password");
    container.querySelector<HTMLInputElement>('[name="confirmation"]')!.click();
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  expect(save).toHaveBeenCalledWith("article", "later-page", expect.objectContaining({ expected_revision: 3,
    payload: expect.objectContaining({ slug: "later-page", title: "Исправленный материал" }) }));
});

it("clears an unsaved new article when starting another new article", () => {
  act(() => root.render(createElement(ManagedContentEditor, { initialError: false, initialItems: [] })));
  act(() => chooseContentKind("article"));
  act(() => value("title", "Несохранённый заголовок"));
  act(() => Array.from(container.querySelectorAll("button")).find(item => item.textContent?.includes("Новая статья"))!.click());
  expect(container.querySelector('[name="title"]')).toHaveProperty("value", "");
});

it("preserves an unsaved article draft when its slug changes", () => {
  act(() => root.render(createElement(ManagedContentEditor, { initialError: false, initialItems: [] })));
  act(() => chooseContentKind("article"));
  act(() => {
    value("title", "Проверка транспорта перед покупкой");
    value("summary", "Краткая памятка по осмотру и документам перед сделкой.");
    value("sources", "Госорган | https://example.gov.by/guide");
    value("body", "Сверьте документы, VIN и состояние транспорта до заключения сделки.");
    value("content_key", "vehicle-check");
  });

  act(() => value("content_key", "vehicle-inspection"));

  expect(container.querySelector('[name="title"]')).toHaveProperty("value", "Проверка транспорта перед покупкой");
  expect(container.querySelector('[name="summary"]')).toHaveProperty("value", "Краткая памятка по осмотру и документам перед сделкой.");
  expect(container.querySelector('[name="sources"]')).toHaveProperty("value", "Госорган | https://example.gov.by/guide");
  expect(container.querySelector('[name="body"]')).toHaveProperty("value", "Сверьте документы, VIN и состояние транспорта до заключения сделки.");
  expect(container.querySelector('[name="content_key"]')).toHaveProperty("value", "vehicle-inspection");
});
