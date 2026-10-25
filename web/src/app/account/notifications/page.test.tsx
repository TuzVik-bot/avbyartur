import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  notifications: vi.fn(),
  notificationPreferences: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));

import NotificationsPage from "./page";

describe("notifications page", () => {
  it("loads the real notification inbox endpoint and renders unread state", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.test" } });
    mocks.notificationPreferences.mockResolvedValueOnce({ preferences: { web_enabled: true, email_enabled: false, revision: 2, email_verified: false, email_delivery_configured: false } });
    mocks.notifications.mockResolvedValueOnce({
      unread_count: 1,
      items: [{
        id: "notification-1",
        saved_search_id: "search-1",
        conversation_id: null,
        listing_id: "listing-1",
        title: "Новое объявление",
        body: "BMW 320d подходит под ваш поиск.",
        url: "/cars?q=bmw",
        listings: [{ id: "listing-1", title: "BMW 320d", url: "/cars/bmw-320d" }],
        total_count: 1,
        read_at: null,
        created_at: "2026-09-30T10:00:00Z"
      }]
    });

    const html = renderToStaticMarkup(await NotificationsPage());

    expect(mocks.notifications).toHaveBeenCalledWith({ limit: 50 });
    expect(html).toContain("Новое объявление");
    expect(mocks.notificationPreferences).toHaveBeenCalledOnce();
    expect(html).toContain("Настройки уведомлений");
    expect(html).toContain("Email доступен при подтверждённом адресе и настроенной доставке");
    expect(html).toContain('href="/account/notifications"');
  });

  it("keeps a retryable empty state when the endpoint is unavailable", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.test" } });
    mocks.notifications.mockRejectedValueOnce(new Error("offline"));
    mocks.notificationPreferences.mockRejectedValueOnce(new Error("offline"));

    const html = renderToStaticMarkup(await NotificationsPage());

    expect(html).toContain("Не удалось загрузить уведомления. Повторите попытку.");
    expect(html).toContain("Обновить");
  });
});
