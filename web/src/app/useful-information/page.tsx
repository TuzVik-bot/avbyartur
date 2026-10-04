import { UsefulInformationList } from "@/components/informational-page";
import { ARTICLE_TOPIC_LABELS, type ArticleTopic } from "@/lib/content";
import { contentServerApi } from "@/lib/content-server";

export const metadata = { title: "Полезная информация", robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } } };

type SearchParams = Record<string, string | string[] | undefined>;

function requestedTopic(value: string | string[] | undefined): ArticleTopic | null {
  return typeof value === "string" && Object.hasOwn(ARTICLE_TOPIC_LABELS, value) ? value as ArticleTopic : null;
}

export default async function UsefulInformationPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const { topic: rawTopic } = await searchParams;
  const selectedTopic = requestedTopic(rawTopic);
  try {
    const result = await contentServerApi.articles(selectedTopic || undefined);
    return <UsefulInformationList items={result.items} selectedTopic={selectedTopic} />;
  } catch {
    return <UsefulInformationList items={[]} selectedTopic={selectedTopic} unavailable />;
  }
}
