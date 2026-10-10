import { UsefulInformationList } from "@/components/informational-page";
import { ARTICLE_TOPIC_LABELS, type ArticleTopic } from "@/lib/content";
import { contentServerApi } from "@/lib/content-server";
import { redirect } from "next/navigation";

export const metadata = { title: "Полезная информация", robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } } };

type SearchParams = Record<string, string | string[] | undefined>;

function requestedTopic(value: string | string[] | undefined): ArticleTopic | null {
  return typeof value === "string" && Object.hasOwn(ARTICLE_TOPIC_LABELS, value) ? value as ArticleTopic : null;
}

function requestedPage(value: string | string[] | undefined): number {
  if (typeof value !== "string" || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : 1;
}

function pageUrl(topic: ArticleTopic | null, page: number): string {
  const query = new URLSearchParams({ ...(topic ? { topic } : {}), ...(page > 1 ? { page: String(page) } : {}) });
  return `/useful-information${query.size ? `?${query}` : ""}`;
}

export default async function UsefulInformationPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const { topic: rawTopic, page: rawPage } = await searchParams;
  const selectedTopic = requestedTopic(rawTopic);
  const page = requestedPage(rawPage);
  let result;
  try {
    result = await contentServerApi.articles(selectedTopic || undefined, page);
  } catch {
    return <UsefulInformationList items={[]} selectedTopic={selectedTopic} unavailable />;
  }
  const pageCount = Math.max(1, Math.ceil(result.total / result.page_size));
  if (page > pageCount) redirect(pageUrl(selectedTopic, pageCount));
  return <UsefulInformationList items={result.items} selectedTopic={selectedTopic}
    page={result.page} pageCount={pageCount} />;
}
