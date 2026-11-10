import type { ReactNode } from "react";
import styles from "./informational-page.module.css";

export type InformationalPageProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  notice?: ReactNode;
  sections?: readonly { id: string; title: string }[];
  children: ReactNode;
};

/** Shared reading layout for public guides and documents. */
export function InformationalPage({ eyebrow, title, description, notice, sections = [], children }: InformationalPageProps) {
  return (
    <div className={`page-width info-page ${styles.page}`}>
      <header className={`page-head ${styles.header}`}>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </header>
      <div className={sections.length ? styles.layout : styles.single}>
        {sections.length > 0 && <nav className={styles.contents} aria-label="На этой странице">
          <p>На этой странице</p>
          <ol>{sections.map((section) => <li key={section.id}><a href={`#${section.id}`}>{section.title}</a></li>)}</ol>
        </nav>}
        <div className={styles.reading}>
          {notice && <div className={`info-notice ${styles.notice}`}>{notice}</div>}
          <div className={`info-content ${styles.content}`}>{children}</div>
        </div>
      </div>
    </div>
  );
}
