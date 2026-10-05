import type { ReactNode } from "react";
import Image from "next/image";

export type InformationalPageProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  notice?: ReactNode;
  visual?: { src: string; alt: string };
  children: ReactNode;
};

/** Shared shell for public information pages in the closed pilot. */
export function InformationalPage({ eyebrow, title, description, notice, visual, children }: InformationalPageProps) {
  return (
    <div className={`page-width info-page${visual ? " info-page-with-visual" : ""}`}>
      <header className="page-head">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </header>
      {visual && <div className="info-visual"><Image src={visual.src} alt={visual.alt} width={1200} height={800} sizes="(max-width: 640px) 100vw, 40vw" /></div>}
      {notice && <div className="notice info-notice">{notice}</div>}
      <div className="info-content">{children}</div>
    </div>
  );
}
