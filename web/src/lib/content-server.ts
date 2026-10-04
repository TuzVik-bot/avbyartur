import { serverApiRequest } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";
import type { ArticlePublicEnvelope, ArticleTopic, ContentKind } from "@/lib/content";

export type ArticleList = components["schemas"]["ManagedArticleListOut"];

export const contentServerApi = {
  list: () => serverApiRequest<components["schemas"]["ManagedContentListOut"]>("admin/content?page_size=100"),
  public: (kind: ContentKind, key: string) => serverApiRequest<components["schemas"]["ManagedContentPublicEnvelope"]>(`content/${kind}/${encodeURIComponent(key)}`),
  articles: (topic?: ArticleTopic, page = 1) => {
    const query = new URLSearchParams({ ...(topic ? { topic } : {}), ...(page > 1 ? { page: String(page) } : {}) }).toString();
    return serverApiRequest<ArticleList>(`content/articles${query ? `?${query}` : ""}`);
  },
  article: (slug: string) => serverApiRequest<ArticlePublicEnvelope>(`content/article/${encodeURIComponent(slug)}`)
};
