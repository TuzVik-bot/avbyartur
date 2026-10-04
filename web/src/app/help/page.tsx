import type { Metadata } from "next";
import { BookOpen, FileText, ShieldCheck } from "lucide-react";
import { FAQ_TOPICS } from "@/components/faq-topics";

export const metadata: Metadata = { title: "Помощь" };

export default function HelpPage() {
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Справка</p><h1>Помощь и правила пилота</h1><p>Ответы о подаче, проверке и контактных данных.</p></header>
      <div className="help-grid">
        {FAQ_TOPICS.map((topic, index) => <details className="help-item" key={topic.title} open={index === 0}>
          <summary>{index === 0 ? <BookOpen size={17} /> : index === FAQ_TOPICS.length - 1 ? <FileText size={17} /> : <ShieldCheck size={17} />} {topic.title}</summary>
          <p>{topic.text}</p>
        </details>)}
      </div>
    </div>
  );
}
