import Link from "next/link";
import { notFound } from "next/navigation";
import { InformationalPage, UsefulInformationArticle } from "@/components/informational-page";
import { ApiClientError } from "@/lib/api";
import { contentServerApi } from "@/lib/content-server";

export const metadata = { title: "Полезная информация", robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } } };

export default async function UsefulInformationArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  try {
    const result = await contentServerApi.article(slug);
    return <UsefulInformationArticle article={result.content.payload} />;
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) notFound();
    return <InformationalPage title="Материал временно недоступен" description="Не удалось загрузить статью. Обновите страницу позже.">
      <Link href="/useful-information">Вернуться к полезной информации</Link>
    </InformationalPage>;
  }
}
