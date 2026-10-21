import { expect, it, vi } from "vitest";
import * as serverApi from "@/lib/server-api";
import { contentServerApi } from "@/lib/content-server";

vi.mock("@/lib/server-api", () => ({ serverApiRequest: vi.fn() }));

it("loads published articles with the selected topic through the internal server API", async () => {
  const method = (contentServerApi as unknown as { articles?: (topic?: string) => Promise<unknown> }).articles;
  expect(method).toBeTypeOf("function");
  if (!method) return;

  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
  await method("vin");
  expect(serverApi.serverApiRequest).toHaveBeenCalledWith("content/articles?topic=vin");
});

it("loads an article detail using an encoded slug", async () => {
  const method = (contentServerApi as unknown as { article?: (slug: string) => Promise<unknown> }).article;
  expect(method).toBeTypeOf("function");
  if (!method) return;

  vi.mocked(serverApi.serverApiRequest).mockResolvedValueOnce({ content: {}, indexable: false });
  await method("inspection-before-buying");
  expect(serverApi.serverApiRequest).toHaveBeenCalledWith("content/article/inspection-before-buying");
});
