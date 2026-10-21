import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { notFound } from "next/navigation";
import { InformationalPage } from "@/components/informational-page";
import { editorialArticles, getEditorialArticle } from "@/lib/editorial-articles";
import { type ArticleCard, loadArticleCards, loadManagedArticle, splitArticleParagraphs } from "@/lib/public-articles";
import { ARTICLE_TOPIC_LABELS, type ArticlePublicItem } from "@/lib/content";
import { editorialContentUpdated, editorialGuideActions } from "@/lib/editorial-guide-actions";
import { siteUrl } from "@/lib/site-config";
import styles from "../articles.module.css";

type ArticlePageProps = { params: Promise<{ slug: string }> };

const dateFormatter = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Minsk" });

function formatUpdated(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : dateFormatter.format(date);
}

export function generateStaticParams() {
  return editorialArticles.map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: ArticlePageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = getEditorialArticle(slug);
  if (!article) {
    const managed = await loadManagedArticle(slug);
    if (!managed) return { title: "Статья не найдена", robots: { index: false, follow: false } };
    return {
      title: managed.payload.title,
      description: managed.payload.summary,
      alternates: { canonical: siteUrl(`/useful-information/articles/${managed.key}`) },
    };
  }

  return {
    title: article.title,
    description: article.description,
    alternates: { canonical: siteUrl(`/useful-information/articles/${article.slug}`) },
  };
}

export default async function ArticleDetailPage({ params }: ArticlePageProps) {
  const { slug } = await params;
  const article = getEditorialArticle(slug);
  if (!article) {
    const managed = await loadManagedArticle(slug);
    if (!managed) notFound();
    const cards = await loadArticleCards();
    return <ManagedArticleView article={managed} related={cards.filter((item) => item.slug !== managed.key)} />;
  }

  const relatedArticles = editorialArticles.filter((item) => item.slug !== article.slug);

  return (
    <InformationalPage eyebrow={article.section} title={article.title} description={article.description}>
      <nav className={styles.breadcrumbs} aria-label="Хлебные крошки">
        <Link href="/useful-information/articles"><ArrowLeft size={15} aria-hidden="true" /> Все статьи</Link>
      </nav>

      <p className={styles.articleByline}>Редакционный материал · Обновлено {editorialContentUpdated}</p>

      <article className={styles.articleBody}>
        {article.sections.map((section) => (
          <section key={section.heading}>
            <h2>{section.heading}</h2>
            {section.blocks.map((block, index) => block.type === "paragraph"
              ? <p key={`${section.heading}-paragraph-${index}`}>{block.text}</p>
              : <ul key={`${section.heading}-list-${index}`}>{block.items.map((item) => <li key={item}>{item}</li>)}</ul>)}
          </section>
        ))}
        <p className={styles.closingNote}><strong>{article.closingLabel}</strong> {article.closingText}</p>
      </article>

      <section className={`info-section ${styles.articleNextSteps}`} aria-labelledby="article-next-steps-title">
        <h2 id="article-next-steps-title">Что сделать дальше</h2>
        <div className={styles.articleActions}>
          {editorialGuideActions[article.slug].map((action, index) => (
            <article className={styles.articleAction} key={action.href}>
              <Link className={`button ${index === 0 ? "button-primary" : "button-secondary"}`} href={action.href}>
                {action.label} <ArrowUpRight size={16} aria-hidden="true" />
              </Link>
              <p>{action.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={`info-section ${styles.relatedArticles}`} aria-labelledby="related-articles-title">
        <h2 id="related-articles-title">Другие инструкции</h2>
        <ul>
          {relatedArticles.map((item) => <li key={item.slug}>
            <Link href={`/useful-information/articles/${item.slug}`}>{item.title}</Link>
          </li>)}
        </ul>
      </section>
    </InformationalPage>
  );
}

function ManagedArticleView({ article, related }: { article: ArticlePublicItem; related: readonly ArticleCard[] }) {
  const { payload } = article;
  const updated = formatUpdated(article.updated_at);
  const sources = payload.sources.filter((source) => /^https:\/\//i.test(source.url));

  return (
    <InformationalPage eyebrow={ARTICLE_TOPIC_LABELS[payload.topic] ?? "Полезная информация"} title={payload.title} description={payload.summary}>
      <nav className={styles.breadcrumbs} aria-label="Хлебные крошки">
        <Link href="/useful-information/articles"><ArrowLeft size={15} aria-hidden="true" /> Все статьи</Link>
      </nav>

      <p className={styles.articleByline}>Редакционный материал{updated ? ` · Обновлено ${updated}` : ""}</p>

      <article className={styles.articleBody}>
        {splitArticleParagraphs(payload.body).map((paragraph, index) => (
          <p className={styles.plainParagraph} key={`paragraph-${index}`}>{paragraph}</p>
        ))}
        {sources.length > 0 && (
          <section aria-labelledby="article-sources-title">
            <h2 id="article-sources-title">Источники</h2>
            <ul>
              {sources.map((source) => (
                <li key={source.url}><a href={source.url} rel="noopener noreferrer nofollow" target="_blank">{source.title}</a></li>
              ))}
            </ul>
          </section>
        )}
      </article>

      {related.length > 0 && (
        <section className={`info-section ${styles.relatedArticles}`} aria-labelledby="related-articles-title">
          <h2 id="related-articles-title">Другие инструкции</h2>
          <ul>
            {related.map((item) => <li key={item.slug}>
              <Link href={`/useful-information/articles/${item.slug}`}>{item.title}</Link>
            </li>)}
          </ul>
        </section>
      )}
    </InformationalPage>
  );
}
