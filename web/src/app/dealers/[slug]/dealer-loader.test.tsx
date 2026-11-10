import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ dealer: vi.fn() }));

vi.mock("@/lib/server-api", () => ({ serverApi: mocks, getSavedListingIds: vi.fn(async () => [] as string[]) }));
vi.mock("next/navigation", () => ({ notFound: vi.fn(), redirect: vi.fn() }));

import { generateMetadata } from "./page";

describe("dealer page loader", () => {
  it("loads metadata with the same slug and page as the page body so both share one request", async () => {
    mocks.dealer.mockResolvedValueOnce({
      company: { id: "company-1", slug: "company-one", name: "Company One" },
      listings: { items: [], pagination: { page: 1, page_size: 25, total: 1, pages: 1 } }
    });

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: "company-one" }), searchParams: Promise.resolve({}) });

    expect(mocks.dealer).toHaveBeenCalledWith("company-one", 1);
    expect(metadata.title).toBe("Company One");
  });
});
