import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationsInbox } from "@/components/notifications-inbox";
import { api } from "@/lib/api";
import type { UserNotification } from "@/lib/types";

const notification: UserNotification = {
  id: "notification-1",
  saved_search_id: "search-1",
  listing_id: "listing-1",
  title: "Новое объявление: BMW 320d",
  body: "Нашли автомобиль по вашему сохранённому поиску.",
  url: "/cars?q=bmw",
  read_at: null,
  created_at: "2026-09-30T10:00:00Z"
};

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

describe("NotificationsInbox", () => {
  it("renders unread messages and marks them read through the API", async () => {
    const markRead = vi.spyOn(api, "markNotificationRead").mockResolvedValue({ ok: true });
    await act(async () => { root.render(createElement(NotificationsInbox, { initialItems: [notification], initialUnreadCount: 1 })); });

    expect(container.textContent).toContain("Новое объявление: BMW 320d");
    expect(container.textContent).toContain("Непрочитано: 1");
    const markButton = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Отметить прочитанным"));
    expect(markButton).not.toBeNull();

    await act(async () => { markButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

    expect(markRead).toHaveBeenCalledWith(notification.id);
    expect(container.textContent).toContain("Все сообщения прочитаны");
    expect(container.textContent).not.toContain("Отметить прочитанным");
  });

  it("explains that email delivery is not configured and filters read items", async () => {
    const read = { ...notification, id: "notification-2", read_at: "2026-09-30T11:00:00Z" };
    await act(async () => { root.render(createElement(NotificationsInbox, { initialItems: [notification, read], initialUnreadCount: 1 })); });

    expect(container.textContent).toContain("Email-настройка сохраняется, но письма не отправляются");
    expect(container.textContent).toContain("Новое объявление: BMW 320d");
    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]');
    expect(checkbox).not.toBeNull();
    await act(async () => { checkbox!.click(); });
    expect(container.querySelectorAll(".notification-item")).toHaveLength(1);
    expect(container.querySelector(".notification-item")?.textContent).toContain("Новое объявление: BMW 320d");
  });

  it("keeps a failed initial load distinct from an empty inbox and offers retry", async () => {
    const loadNotifications = vi.spyOn(api, "notifications").mockResolvedValue({ items: [notification], unread_count: 1 });
    await act(async () => { root.render(createElement(NotificationsInbox, { initialItems: [], initialUnreadCount: 0, initialLoadError: true })); });

    expect(container.textContent).toContain("Не удалось загрузить уведомления");
    expect(container.textContent).not.toContain("Пока нет уведомлений");
    const retry = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Повторить"));
    await act(async () => { retry?.click(); });

    expect(loadNotifications).toHaveBeenCalledWith({ limit: 50 });
    expect(container.textContent).toContain("Новое объявление: BMW 320d");
  });
});
