import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  listingAnalytics: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));

import ListingAnalyticsPage from "./page";

const listingId = "7c2a3d4e-5f60-4789-8abc-0123456789ab";
const analytics = {
  listing_id: listingId,
  period: { start: "2026-10-01", end: "2026-10-31" },
  views: 123,
  contact_reveals: 12,
  chats: 4
};

beforeEach(() => {
  mocks.listingAnalytics.mockReset().mockResolvedValue(analytics);
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "seller-1" } });
});

describe("listing analytics page", () => {
  it("keeps the account guard and shows event counts with honest definitions", async () => {
    const html = renderToStaticMarkup(await ListingAnalyticsPage({
      searchParams: Promise.resolve({
        listing_id: listingId,
        date_from: "2026-10-01",
        date_to: "2026-10-31"
      })
    }));

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/listings/analytics");
    expect(mocks.listingAnalytics).toHaveBeenCalledWith(listingId, {
      dateFrom: "2026-10-01",
      dateTo: "2026-10-31"
    });
    expect(html).toContain("123");
    expect(html).toContain("12");
    expect(html).toContain(">4<");
    expect(html).toContain("не число уникальных людей");
    expect(html).toContain("не означает звонок или продажу");
    expect(html).toContain("не подтверждают сделку");
  });

  it.each([
    ["impossible calendar date", "2026-02-30", "2026-03-01"],
    ["reversed range", "2026-10-02", "2026-10-01"],
    ["range wider than 367 calendar days", "2025-10-01", "2026-10-03"]
  ])("rejects %s before calling the analytics API", async (_label, dateFrom, dateTo) => {
    const html = renderToStaticMarkup(await ListingAnalyticsPage({
      searchParams: Promise.resolve({ listing_id: listingId, date_from: dateFrom, date_to: dateTo })
    }));

    expect(mocks.listingAnalytics).not.toHaveBeenCalled();
    expect(html).toContain("Проверьте даты периода");
    expect(html).toContain(`name="listing_id" value="${listingId}"`);
  });

  it("accepts the API limit of 367 inclusive calendar days", async () => {
    const html = renderToStaticMarkup(await ListingAnalyticsPage({
      searchParams: Promise.resolve({
        listing_id: listingId,
        date_from: "2025-10-01",
        date_to: "2026-10-02"
      })
    }));

    expect(mocks.listingAnalytics).toHaveBeenCalledWith(listingId, {
      dateFrom: "2025-10-01",
      dateTo: "2026-10-02"
    });
    expect(html).toContain("Период:");
  });

  it("offers an API retry that preserves listing and valid period parameters", async () => {
    mocks.listingAnalytics.mockRejectedValueOnce(new Error("offline"));

    const html = renderToStaticMarkup(await ListingAnalyticsPage({
      searchParams: Promise.resolve({
        listing_id: listingId,
        date_from: "2026-10-01",
        date_to: "2026-10-31"
      })
    }));

    expect(html).toContain("Не удалось загрузить статистику");
    expect(html).toContain("Повторить загрузку");
    expect(html).toContain(`listing_id=${listingId}`);
    expect(html).toContain("date_from=2026-10-01");
    expect(html).toContain("date_to=2026-10-31");
  });
});
