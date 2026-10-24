"use client";

import { useState, type ReactNode } from "react";

export function FooterGroup({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className={`footer-group${expanded ? " is-expanded" : ""}`} aria-labelledby={`footer-${id}`}>
      <h2 className="footer-group-title" id={`footer-${id}`}>
        <span className="footer-desktop-title">{title}</span>
        <button className="footer-group-toggle" type="button" aria-expanded={expanded} aria-controls={`footer-${id}-links`} onClick={() => setExpanded(!expanded)}>
          {title}<span aria-hidden="true">{expanded ? "−" : "+"}</span>
        </button>
      </h2>
      <div className="footer-group-content" id={`footer-${id}-links`}>{children}</div>
    </section>
  );
}
