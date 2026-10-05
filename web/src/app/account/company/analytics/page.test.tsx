import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn(), requireSession: vi.fn() }));
vi.mock("@/lib/server-api", () => ({ serverApiRequest: mocks.request }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));

import DealerAnalyticsPage from "./page";

beforeEach(() => {
  mocks.request.mockReset().mockResolvedValue({ items: [] });
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "unlinked-user" } });
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.request.mockReset();
  mocks.requireSession.mockReset();
});

describe("dealer analytics page", () => {
  it("loads a company-scoped analytics date range and renders the aggregate counts", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "owner-user" } });
    mocks.request
      .mockResolvedValueOnce({ items: [{ user_id: "owner-user", status: "active", role: "owner" }] })
      .mockResolvedValueOnce({
        period: { start: "2026-09-01", end: "2026-09-30" },
        totals: { listings: 8, active_listings: 5, contact_reveals: 11, chats: 4, views: 230 },
        items: [
          { listing_id: "listing-1", title: "Toyota Camry", status: "active", contact_reveals: 3, chats: 2, views: 70 },
          { listing_id: "listing-2", title: "Skoda Octavia", status: "pending_review", contact_reveals: 0, chats: 0, views: 0 },
          { listing_id: "listing-3", title: "Volvo XC60", status: "rejected", contact_reveals: 0, chats: 0, views: 0 }
        ]
      });
    const html = renderToStaticMarkup(await DealerAnalyticsPage({ searchParams: Promise.resolve({ from: "2026-09-01", to: "2026-09-30" }) }));
    expect(mocks.requireSession).toHaveBeenCalledWith("/account/company/analytics");
    expect(mocks.request).toHaveBeenNthCalledWith(1, "dealer/team");
    expect(mocks.request).toHaveBeenNthCalledWith(2, "dealer/analytics?from=2026-09-01&to=2026-09-30");
    expect(html).toContain("Показов телефона");
    expect(html).toContain("230");
    expect(html).toContain("Toyota Camry");
    expect(html).toContain('class="status-pill status-active">Опубликовано</span>');
    expect(html).toContain('class="status-pill status-pending_review">На проверке</span>');
    expect(html).toContain('class="status-pill status-rejected">Нужно исправить</span>');
    expect(html).not.toContain(">pending_review<");
  });

  it("does not request analytics when the signed-in user has no active company membership", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "unlinked-user" } });
    mocks.request.mockResolvedValueOnce({ items: [] });
    const html = renderToStaticMarkup(await DealerAnalyticsPage({ searchParams: Promise.resolve({}) }));
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(html).toContain("не найдена активная связь с компанией");
  });
});
