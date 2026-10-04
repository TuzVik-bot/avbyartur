import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ModerationPage from "@/app/moderation/page";

const mocks = vi.hoisted(() => ({
  moderationListings: vi.fn(),
  moderationCompanies: vi.fn(),
  moderationReports: vi.fn(),
  requireSession: vi.fn(),
  redirect: vi.fn((href: string): never => { throw new Error(`REDIRECT:${href}`); })
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/components/account-nav", () => ({ AccountNav: () => null }));
vi.mock("@/components/moderation-actions", () => ({
  CompanyModerationActions: () => null,
  ListingModerationActions: () => <div data-testid="listing-moderation-actions" />,
  ReportResolution: () => null
}));
vi.mock("@/components/moderation-listing-preview", () => ({ ModerationListingPreview: () => null }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.moderationListings.mockReset().mockResolvedValue({ items: [], pagination: { page: 1, page_size: 50, total: 120, pages: 3 } });
  mocks.moderationCompanies.mockReset().mockResolvedValue({ items: [] });
  mocks.moderationReports.mockReset().mockResolvedValue({ items: [] });
  mocks.requireSession.mockReset().mockResolvedValue({ user: { role: "moderator" } });
  mocks.redirect.mockClear();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("moderation listing queues", () => {
  const render = async (params: { queue?: string; page?: string } = {}) => {
    const page = await ModerationPage({ searchParams: Promise.resolve(params) });
    await act(async () => { root.render(page); });
  };

  it("requests active separately and keeps the default queue on pending review", async () => {
    await render({ queue: "active" });
    expect(mocks.moderationListings).toHaveBeenLastCalledWith("active", 1);
    expect(container.querySelector('a[href="/moderation?queue=active"]')?.getAttribute("aria-current")).toBe("page");

    await render();
    expect(mocks.moderationListings).toHaveBeenLastCalledWith("pending_review", 1);
    expect(container.querySelector('a[href="/moderation?queue=listings"]')?.getAttribute("aria-current")).toBe("page");
  });

  it("passes the selected page and keeps the queue in pagination links", async () => {
    await render({ queue: "listings", page: "2" });
    expect(mocks.moderationListings).toHaveBeenLastCalledWith("pending_review", 2);
    expect(container.querySelector('.pagination a[href="/moderation?queue=listings"]')?.textContent).toContain("Назад");
    expect(container.querySelector('.pagination a[href="/moderation?queue=listings&page=3"]')?.textContent).toContain("Дальше");
    expect(container.textContent).toContain("Страница 2 из 3");

    await render({ queue: "active", page: "2" });
    expect(mocks.moderationListings).toHaveBeenLastCalledWith("active", 2);
    expect(container.querySelector('.pagination a[href="/moderation?queue=active"]')?.textContent).toContain("Назад");
    expect(container.querySelector('.pagination a[href="/moderation?queue=active&page=3"]')?.textContent).toContain("Дальше");
  });

  it("redirects invalid and out-of-range pages to a valid queue page", async () => {
    await expect(ModerationPage({ searchParams: Promise.resolve({ queue: "active", page: "0" }) }))
      .rejects.toThrow("REDIRECT:/moderation?queue=active");
    expect(mocks.moderationListings).not.toHaveBeenCalled();

    mocks.moderationListings.mockResolvedValueOnce({ items: [], pagination: { page: 9, page_size: 50, total: 120, pages: 3 } });
    await expect(ModerationPage({ searchParams: Promise.resolve({ queue: "active", page: "9" }) }))
      .rejects.toThrow("REDIRECT:/moderation?queue=active&page=3");
    expect(mocks.moderationListings).toHaveBeenLastCalledWith("active", 9);
  });

  it("keeps the existing listing row unchanged when there are no risk signals", async () => {
    mocks.moderationListings.mockResolvedValueOnce({
      items: [{
        id: "listing-empty-signals",
        title: "Skoda Octavia",
        seller: { name: "Продавец" },
        revision: 1,
        status: "pending_review",
        risk_signals: []
      }],
      pagination: { page: 1, page_size: 50, total: 1, pages: 1 }
    });

    await render();

    expect(container.querySelector(".moderation-risk-signals")).toBeNull();
    expect(container.querySelector(".moderation-item h2")?.textContent).toBe("Skoda Octavia");
    expect(container.querySelector(".moderation-item")).not.toBeNull();
    const row = container.querySelector(".moderation-item");
    expect(row?.children).toHaveLength(2);
    expect(row?.children[1]).toBe(container.querySelector("[data-testid='listing-moderation-actions']"));
  });

  it("keeps moderation grid cells in the same positions with missing, empty, or populated signals", async () => {
    mocks.moderationListings.mockResolvedValueOnce({
      items: [
        { id: "without-signals", title: "Авто без поля", seller: { name: "Продавец" }, revision: 1, status: "pending_review" },
        { id: "empty-signals", title: "Авто с пустым списком", seller: { name: "Продавец" }, revision: 1, status: "pending_review", risk_signals: [] },
        { id: "with-signals", title: "Авто с сигналом", seller: { name: "Продавец" }, revision: 1, status: "pending_review", risk_signals: [{ code: "external_link", severity: "low", summary: "В описании ссылка" }] }
      ],
      pagination: { page: 1, page_size: 50, total: 3, pages: 1 }
    });

    await render();

    const rows = [...container.querySelectorAll<HTMLElement>(".moderation-item")];
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      expect(row.classList.contains("moderation-item")).toBe(true);
      expect(row.children).toHaveLength(2);
      expect(row.children[1].getAttribute("data-testid")).toBe("listing-moderation-actions");
    }
    expect(rows[0].querySelector(".moderation-risk-signals")).toBeNull();
    expect(rows[1].querySelector(".moderation-risk-signals")).toBeNull();
    expect(rows[2].querySelector(".moderation-risk-signals")).not.toBeNull();
  });

  it("shows localized advisory risk signals without changing moderation actions", async () => {
    mocks.moderationListings.mockResolvedValueOnce({
      items: [{
        id: "listing-with-signals",
        title: "Skoda Octavia",
        seller: { name: "Продавец" },
        revision: 2,
        status: "pending_review",
        risk_signals: [
          {
            code: "duplicate_vin",
            severity: "high",
            summary: "VIN совпадает еще с 2 активными или ожидающими объявлениями",
            related_count: 2
          },
          {
            code: "external_link",
            severity: "low",
            summary: "В описании обнаружена внешняя ссылка"
          }
        ]
      }],
      pagination: { page: 1, page_size: 50, total: 1, pages: 1 }
    });

    await render();

    const signals = container.querySelector(".moderation-risk-signals");
    expect(signals).not.toBeNull();
    expect(signals?.getAttribute("aria-label")).toBe("Подсказки модератору");
    expect(signals?.textContent).toContain("Совпадение VIN");
    expect(signals?.textContent).toContain("Высокая важность");
    expect(signals?.textContent).toContain("Связанных объявления: 2");
    expect(signals?.textContent).toContain("Внешняя ссылка");
    expect(signals?.textContent).toContain("Низкая важность");
    expect(signals?.textContent).toContain("Подсказки для модератора, не автоматическое решение.");
    expect(container.querySelector(".moderation-item")).not.toBeNull();
    expect(container.querySelector("[data-testid='listing-moderation-actions']")).not.toBeNull();
  });

  it("does not expose untrusted signal summaries that contain raw VIN or phone data", async () => {
    const rawVin = "1HGCM82633A004352";
    const rawPhone = "+375 (29) 123-45-67";
    mocks.moderationListings.mockResolvedValueOnce({
      items: [{
        id: "listing-with-sensitive-summaries",
        title: "Skoda Octavia",
        seller: { name: "Продавец" },
        revision: 1,
        status: "pending_review",
        risk_signals: [
          { code: "duplicate_vin", severity: "high", summary: `Совпавший VIN: ${rawVin}`, related_count: 1 },
          { code: "external_link", severity: "low", summary: `Телефон продавца: ${rawPhone}` }
        ]
      }],
      pagination: { page: 1, page_size: 50, total: 1, pages: 1 }
    });

    await render();

    const signals = container.querySelector(".moderation-risk-signals");
    expect(signals?.textContent).not.toContain(rawVin);
    expect(signals?.textContent).not.toContain(rawPhone);
    expect(signals?.textContent).toContain("Данные VIN совпадают с другими объявлениями.");
    expect(signals?.textContent).toContain("В описании найдена внешняя ссылка.");
  });

  it("renders an explicitly supplied zero related count", async () => {
    mocks.moderationListings.mockResolvedValueOnce({
      items: [{
        id: "listing-zero-related-count",
        title: "Skoda Octavia",
        seller: { name: "Продавец" },
        revision: 1,
        status: "pending_review",
        risk_signals: [{ code: "external_link", severity: "low", summary: "Не используется в интерфейсе", related_count: 0 }]
      }],
      pagination: { page: 1, page_size: 50, total: 1, pages: 1 }
    });

    await render();

    expect(container.querySelector(".moderation-risk-related-count")?.textContent).toBe("Связанных объявлений: 0");
  });
});
