import { serverApiRequest } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";
import type { ArticlePublicEnvelope, ArticleTopic, ContentKind } from "@/lib/content";

export type ArticleList = components["schemas"]["ManagedArticleListOut"];

function adminContentPage(page: number) {
  return serverApiRequest<components["schemas"]["ManagedContentListOut"]>(`admin/content?page=${page}&page_size=100`);
}

export const contentServerApi = {
  list: () => adminContentPage(1),
  listAll: async () => {
    const first = await adminContentPage(1);
    const items = [...first.items];
    const pageCount = Math.ceil(first.total / first.page_size);
    for (let page = 2; page <= pageCount; page += 1) {
      const result = await adminContentPage(page);
      items.push(...result.items);
    }
    return items;
  },
  public: (kind: ContentKind, key: string) => serverApiRequest<components["schemas"]["ManagedContentPublicEnvelope"]>(`content/${kind}/${encodeURIComponent(key)}`),
  articles: (topic?: ArticleTopic, page = 1) => {
    const query = new URLSearchParams({ ...(topic ? { topic } : {}), ...(page > 1 ? { page: String(page) } : {}) }).toString();
    return serverApiRequest<ArticleList>(`content/articles${query ? `?${query}` : ""}`);
  },
  article: (slug: string) => serverApiRequest<ArticlePublicEnvelope>(`content/article/${encodeURIComponent(slug)}`)
};
