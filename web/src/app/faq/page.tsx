import type { Metadata } from "next";
import Link from "next/link";
import { FAQ_TOPICS } from "@/components/faq-topics";
import { InformationalPage } from "@/components/informational-page";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Ответы о поиске, аккаунте, объявлениях и безопасности.";
export const metadata: Metadata = { title: "Частые вопросы", description, alternates: { canonical: siteUrl("/faq") }, openGraph: buildOpenGraph({ title: "Частые вопросы", description, path: "/faq" }) };

export default function Page() {
  return (
    <InformationalPage eyebrow="Справка" title="Частые вопросы" description="Ответы о поиске, аккаунте, объявлениях и безопасности." sections={[{ id: "questions", title: "Вопросы и ответы" }, { id: "more", title: "Другие разделы" }]}>
      <section className="info-section">
        <h2 id="questions">Вопросы и ответы</h2>
        <div className="help-grid">{FAQ_TOPICS.map((topic, index) => (
          <details className="help-item" key={topic.title} open={index === 0}>
            <summary>{topic.title}</summary><p>{topic.text}</p>
          </details>
        ))}</div>
      </section>
      <section className="info-section">
        <h2 id="more">Другие разделы</h2>
        <p>Подробная инструкция поможет подготовить объявление, а раздел поддержки объяснит, как сообщить о проблеме.</p>
        <div className="info-links"><Link className="button button-secondary" href="/submitting-advert">Подача объявления</Link><Link className="button button-secondary" href="/support">Поддержка</Link><Link className="button button-secondary" href="/commenting-rules">Отзывы и общение</Link></div>
      </section>
    </InformationalPage>
  );
}
