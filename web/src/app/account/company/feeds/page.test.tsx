import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn(), requireSession: vi.fn() }));
vi.mock("@/lib/server-api", () => ({ serverApiRequest: mocks.request }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/components/account-nav", () => ({ AccountNav: () => <nav /> }));
vi.mock("@/components/dealer-feeds", () => ({
  DealerFeeds: ({ initialFeeds }: { initialFeeds: { id: string }[] | null }) =>
    <div data-feed-ids={initialFeeds?.map((feed) => feed.id).join(",") ?? "unavailable"} />,
}));

import DealerFeedsPage from "./page";

beforeEach(() => {
  mocks.request.mockReset();
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "unlinked-user" } });
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.request.mockReset();
  mocks.requireSession.mockReset();
});

describe("dealer feeds page", () => {
  it.each(["owner", "admin", "seller", "viewer"])("loads company feeds on the initial %s page", async (role) => {
    mocks.requireSession.mockResolvedValue({ user: { id: `${role}-user` } });
    mocks.request
      .mockResolvedValueOnce({ items: [{ user_id: `${role}-user`, status: "active", role }] })
      .mockResolvedValueOnce({ items: [{ id: "feed-1" }] });

    const html = renderToStaticMarkup(await DealerFeedsPage());

    expect(mocks.request).toHaveBeenNthCalledWith(1, "dealer/team");
    expect(mocks.request).toHaveBeenNthCalledWith(2, "dealer/feeds");
    expect(html).toContain('data-feed-ids="feed-1"');
  });

  it("does not load feeds when the signed-in user has no active company role", async () => {
    mocks.request.mockResolvedValueOnce({ items: [{ user_id: "other-user", status: "active", role: "owner" }] });

    const html = renderToStaticMarkup(await DealerFeedsPage());

    expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(html).toContain('data-feed-ids=""');
  });
});
