import type { Metadata } from "next";
import { BookOpen, Cookie, FileText, MessageCircleQuestion, ShieldCheck } from "lucide-react";
import { FAQ_TOPICS } from "@/components/faq-topics";
import { InformationalPage } from "@/components/informational-page";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Ответы на частые вопросы об Авторынке: подача и модерация объявлений, безопасность сделки, контакты продавцов и работа с компанией.";
export const metadata: Metadata = {
  title: "Частые вопросы",
  description,
  alternates: { canonical: siteUrl("/faq") },
  openGraph: buildOpenGraph({ title: "Частые вопросы", description, path: "/faq" }),
};

function iconForTopic(index: number) {
  if (index === 0) return <BookOpen size={17} aria-hidden="true" />;
  if (index === 3) return <MessageCircleQuestion size={17} aria-hidden="true" />;
  if (index === 4) return <Cookie size={17} aria-hidden="true" />;
  if (index === FAQ_TOPICS.length - 1) return <FileText size={17} aria-hidden="true" />;
  return <ShieldCheck size={17} aria-hidden="true" />;
}

export default function FaqPage() {
  return (
    <InformationalPage eyebrow="Справка" title="Частые вопросы" description="Ответы о входе, подаче, проверке и контактных данных в закрытом пилоте.">
      <div className="help-grid">
        {FAQ_TOPICS.map((topic, index) => (
          <details className="help-item" key={topic.title} open={index === 0}>
            <summary>{iconForTopic(index)} {topic.title}</summary>
            <p>{topic.text}</p>
          </details>
        ))}
      </div>
    </InformationalPage>
  );
}
