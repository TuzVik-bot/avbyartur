import { expect, it, vi } from "vitest";
import * as serverApi from "@/lib/server-api";
import { contentServerApi } from "@/lib/content-server";

vi.mock("@/lib/server-api", () => ({ serverApiRequest: vi.fn() }));

it("loads every admin content page on the initial server render", async () => {
  const listAll = (contentServerApi as unknown as { listAll?: () => Promise<unknown[]> }).listAll;
  expect(listAll).toBeTypeOf("function");
  if (!listAll) return;

  const firstPage = { items: Array.from({ length: 100 }, (_, index) => ({ key: `article-${index}` })), total: 101, page: 1, page_size: 100 };
  const secondPage = { items: [{ key: "article-100" }], total: 101, page: 2, page_size: 100 };
  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

  const result = await listAll();

  expect(result).toHaveLength(101);
  expect(serverApi.serverApiRequest).toHaveBeenNthCalledWith(1, "admin/content?page=1&page_size=100");
  expect(serverApi.serverApiRequest).toHaveBeenNthCalledWith(2, "admin/content?page=2&page_size=100");
});

it("loads published articles with the selected topic through the internal server API", async () => {
  const method = (contentServerApi as unknown as { articles?: (topic?: string) => Promise<unknown> }).articles;
  expect(method).toBeTypeOf("function");
  if (!method) return;

  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
  await method("vin");
  expect(serverApi.serverApiRequest).toHaveBeenCalledWith("content/articles?topic=vin");
});

it("requests a later page while retaining the topic filter", async () => {
  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce({ items: [], total: 40, page: 2, page_size: 20 });
  await contentServerApi.articles("vin", 2);
  expect(serverApi.serverApiRequest).toHaveBeenCalledWith("content/articles?topic=vin&page=2");
});

it("loads an article detail using an encoded slug", async () => {
  const method = (contentServerApi as unknown as { article?: (slug: string) => Promise<unknown> }).article;
  expect(method).toBeTypeOf("function");
  if (!method) return;

  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce({ content: {}, indexable: false });
  await method("inspection-before-buying");
  expect(serverApi.serverApiRequest).toHaveBeenCalledWith("content/article/inspection-before-buying");
});
