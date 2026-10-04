import type { ReactNode } from "react";

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
