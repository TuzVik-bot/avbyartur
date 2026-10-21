import { apiRequest } from "@/lib/api";
import type { components } from "@/lib/types.generated";

export type ContentItem = components["schemas"]["ManagedContentOut"];
export type ContentKind = ContentItem["kind"];
export type ContentVersion = components["schemas"]["ManagedContentVersionOut"];
export type ContentChange = components["schemas"]["ManagedContentChangeInput"];
export type ArticleSummary = components["schemas"]["ManagedArticleSummaryOut"];
export type ArticleTopic = ArticleSummary["topic"];
export const ARTICLE_TOPIC_LABELS: Record<ArticleTopic, string> = {
  vehicle_selection: "Выбор транспорта",
  inspection: "Осмотр перед покупкой",
  vin: "Проверка VIN",
  transaction: "Оформление сделки",
  credit_leasing: "Кредит и лизинг",
  tires_wheels: "Шины и диски"
};
export const ARTICLE_TOPIC_LINKS: Record<ArticleTopic, { label: string; href: string }> = {
  vehicle_selection: { label: "Перейти к объявлениям транспорта", href: "/cars" },
  inspection: { label: "Посмотреть объявления транспорта", href: "/cars" },
  vin: { label: "Открыть проверку VIN", href: "/vin-check" },
  transaction: { label: "Посмотреть объявления транспорта", href: "/cars" },
  credit_leasing: { label: "Открыть подбор финансирования", href: "/financing" },
  tires_wheels: { label: "Перейти к шинам и дискам", href: "/tires" }
};
export type ArticlePayload = {
  slug: string;
  title: string;
  summary: string;
  topic: ArticleTopic;
  body: string;
  published_at: string | null;
  sources: { title: string; url: string }[];
};
export type ArticlePublicItem = Omit<ContentItem, "payload"> & { kind: "article"; payload: ArticlePayload };
export type ArticlePublicEnvelope = { content: ArticlePublicItem; indexable: boolean };

export const contentApi = {
  list: () => apiRequest<components["schemas"]["ManagedContentListOut"]>("admin/content?page_size=100"),
  save: (kind: ContentKind, key: string, input: ContentChange) => apiRequest<components["schemas"]["ManagedContentEnvelope"]>(`admin/content/${kind}/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(input) }),
  versions: (kind: ContentKind, key: string) => apiRequest<components["schemas"]["ManagedContentVersionsOut"]>(`admin/content/${kind}/${encodeURIComponent(key)}/versions`)
};
