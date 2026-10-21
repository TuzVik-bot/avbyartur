import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";
import { editorialArticles } from "@/lib/editorial-articles";
import { siteUrl } from "@/lib/site-config";
import styles from "./articles.module.css";

export const metadata: Metadata = {
  title: "Статьи и инструкции для автомобилистов",
  description: "Памятки о покупке автомобиля с пробегом, подготовке объявления к продаже и выборе автосервиса.",
  alternates: { canonical: siteUrl("/useful-information/articles") },
};

export default function ArticlesPage() {
  return (
    <InformationalPage
      eyebrow="Полезная информация"
      title="Статьи и инструкции"
      description="Практические памятки для покупки, продажи и обслуживания автомобиля. Проверяйте документы, состояние и условия конкретной сделки отдельно."
    >
      <nav className={styles.breadcrumbs} aria-label="Хлебные крошки">
        <Link href="/useful-information"><ArrowLeft size={15} aria-hidden="true" /> Полезная информация</Link>
      </nav>

      <section className="info-section" aria-label="Список статей">
        <div className={styles.articleGrid}>
          {editorialArticles.map((article) => (
            <article className={`info-card ${styles.articleCard}`} key={article.slug}>
              <p className={styles.articleSection}>{article.section}</p>
              <h2><Link href={`/useful-information/articles/${article.slug}`}>{article.title}</Link></h2>
              <p>{article.description}</p>
              <Link className="text-link" href={`/useful-information/articles/${article.slug}`}>
                Читать статью <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
      </section>

      <p className={styles.relatedLink}>
        Нужна отправная точка для поиска? <Link href="/useful-information#use-case-presets-title">Настройте подборку по своей задаче</Link>.
      </p>
    </InformationalPage>
  );
}
