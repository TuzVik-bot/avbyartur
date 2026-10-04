import type { ReactNode } from "react";
import Link from "next/link";
import { ARTICLE_TOPIC_LABELS, ARTICLE_TOPIC_LINKS, type ArticlePayload, type ArticleSummary, type ArticleTopic } from "@/lib/content";

export type InformationalPageProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  notice?: ReactNode;
  children: ReactNode;
};

/** Shared shell for public information pages in the closed pilot. */
export function InformationalPage({ eyebrow, title, description, notice, children }: InformationalPageProps) {
  return (
    <div className="page-width info-page">
      <header className="page-head">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </header>
      {notice && <div className="notice info-notice">{notice}</div>}
      <div className="info-content">{children}</div>
    </div>
  );
}

function formatArticleDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" })
    .format(new Date(`${value}T00:00:00.000Z`));
}

export function UsefulInformationList({ items, selectedTopic, unavailable = false }: {
  items: ArticleSummary[];
  selectedTopic: ArticleTopic | null;
  unavailable?: boolean;
}) {
  return <InformationalPage eyebrow="Полезная информация" title="Полезная информация"
    description="Практические материалы об осмотре транспорта, сделках, VIN-проверке и финансировании.">
    <nav className="quick-links" aria-label="Темы материалов">
      <Link className="button button-secondary button-small" href="/useful-information" aria-current={selectedTopic === null ? "page" : undefined}>Все темы</Link>
      {Object.entries(ARTICLE_TOPIC_LABELS).map(([topic, label]) => <Link className="button button-secondary button-small"
        key={topic} href={`/useful-information?topic=${topic}`} aria-current={selectedTopic === topic ? "page" : undefined}>{label}</Link>)}
    </nav>
    {unavailable ? <p className="notice" role="alert">Список материалов временно недоступен. Обновите страницу позже.</p>
      : items.length === 0 ? <p className="notice" role="status">Пока нет опубликованных материалов. Материалы появятся после проверки и публикации администратором.</p>
        : <ol className="account-list">{items.map(item => <li className="account-list-item" key={item.slug}>
          <div><p className="eyebrow">{ARTICLE_TOPIC_LABELS[item.topic]}</p><h2><Link href={`/useful-information/${encodeURIComponent(item.slug)}`}>{item.title}</Link></h2>
            <p>{item.summary}</p><time dateTime={item.published_at}>{formatArticleDate(item.published_at)}</time></div>
        </li>)}</ol>}
  </InformationalPage>;
}

function isSafeSource(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password;
  } catch { return false; }
}

export function UsefulInformationArticle({ article }: { article: ArticlePayload }) {
  const related = ARTICLE_TOPIC_LINKS[article.topic];
  const sources = article.sources.filter(source => isSafeSource(source.url));
  return <InformationalPage eyebrow={ARTICLE_TOPIC_LABELS[article.topic]} title={article.title} description={article.summary}>
    <article>
      <p className="muted"><time dateTime={article.published_at || ""}>{article.published_at ? formatArticleDate(article.published_at) : "Дата не указана"}</time></p>
      <div className="article-body" style={{ whiteSpace: "pre-wrap" }}>{article.body}</div>
      {sources.length > 0 && <section aria-labelledby="article-sources-heading"><h2 id="article-sources-heading">Источники</h2>
        <ul>{sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a></li>)}</ul>
      </section>}
      <p className="section"><Link className="button" href={related.href}>{related.label}</Link></p>
      <p><Link href="/useful-information">Все материалы</Link></p>
    </article>
  </InformationalPage>;
}
