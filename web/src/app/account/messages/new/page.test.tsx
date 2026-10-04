import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requireSession: vi.fn().mockResolvedValue({ user: { id: "buyer-1", display_name: "Покупатель", email: "buyer@example.test" } }),
  listing: vi.fn().mockResolvedValue({ listing: { id: "listing-1", slug: "bmw-320d", title: "BMW 320d", status: "active" } }),
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/lib/server-api", () => ({ serverApi: { listing: mocks.listing } }));

import NewMessagePage from "./page";

describe("new message page", () => {
  it("keeps the listing query in the login return path and loads its active title", async () => {
    mocks.listing.mockReset().mockResolvedValue({ listing: { id: "listing-1", slug: "bmw-320d", title: "BMW 320d", status: "active" } });
    const html = renderToStaticMarkup(await NewMessagePage({ searchParams: Promise.resolve({ listing_id: "listing-1" }) }));

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/messages/new?listing_id=listing-1");
    expect(mocks.listing).toHaveBeenCalledWith("listing-1");
    expect(await mocks.listing.mock.results[0]?.value).toEqual({ listing: { id: "listing-1", slug: "bmw-320d", title: "BMW 320d", status: "active" } });
    expect(html).toContain("BMW 320d");
    expect(html).toContain("Здравствуйте! Подскажите");
  });

  it("shows an explanatory state when the contact entry has no listing", async () => {
    mocks.listing.mockClear();
    const html = renderToStaticMarkup(await NewMessagePage({ searchParams: Promise.resolve({}) }));

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/messages/new");
    expect(html).toContain("Выберите объявление");
    expect(html).not.toContain("textarea");
  });
});
