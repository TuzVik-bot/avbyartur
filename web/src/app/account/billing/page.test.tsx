import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireSession: vi.fn(), billingTariffs: vi.fn(), billingOrders: vi.fn() }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/lib/server-api", () => ({ serverApi: { billingTariffs: mocks.billingTariffs, billingOrders: mocks.billingOrders } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));

import BillingPage from "./page";

afterEach(() => vi.restoreAllMocks());

describe("billing page", () => {
  it("shows owner-configured tariff snapshots and keeps checkout disabled", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "user-1" } });
    mocks.billingTariffs.mockResolvedValue([{ id: "tariff-1", code: "highlight-7", service_code: "highlight", name: "Выделение на неделю", amount: "12.50", currency: "BYN", duration_days: 7, listing_quota: null, revision: 2 }]);
    mocks.billingOrders.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    const html = renderToStaticMarkup(await BillingPage({ searchParams: Promise.resolve({ listing_id: "11111111-1111-4111-8111-111111111111" }) }));

    expect(html).toContain("Выделение на неделю");
    expect(html).toContain("12,50 BYN");
    expect(html).toContain("Оформление закрыто");
    expect(html).toContain("подключения рабочего платёжного сервиса");
    expect(html).toContain("Продвижение для объявления");
  });

  it("shows a retryable tariff failure and an empty order history", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "user-1" } });
    mocks.billingTariffs.mockRejectedValue(new Error("offline"));
    mocks.billingOrders.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    const html = renderToStaticMarkup(await BillingPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Не удалось загрузить тарифы");
    expect(html).toContain("Заказов пока нет");
  });
});
