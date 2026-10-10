import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "@/lib/api";
import { contentApi, type ContentItem } from "@/lib/content";

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it("uses the existing admin pagination contract and article filter", async () => {
  vi.mocked(apiRequest).mockResolvedValueOnce({ items: [], total: 0, page: 2, page_size: 100 });
  await contentApi.list({ page: 2, kind: "article" });
  expect(apiRequest).toHaveBeenCalledWith("admin/content?page_size=100&page=2&kind=article");
});

it("loads articles beyond the first admin page without discarding earlier entries", async () => {
  const item = (key: string): ContentItem => ({ id: key, key, kind: "article", status: "draft", revision: 1,
    payload: { title: key }, updated_at: "2026-10-05T00:00:00Z" });
  const firstPage = Array.from({ length: 100 }, (_, index) => item(`article-${index}`));
  const last = item("article-later-page");
  vi.mocked(apiRequest).mockResolvedValueOnce({ items: firstPage, total: 101, page: 1, page_size: 100 })
    .mockResolvedValueOnce({ items: [last], total: 101, page: 2, page_size: 100 });
  expect(await contentApi.listAll("article")).toEqual([...firstPage, last]);
  expect(apiRequest).toHaveBeenNthCalledWith(2, "admin/content?page_size=100&page=2&kind=article");
  expect(apiRequest).toHaveBeenCalledTimes(2);
});
