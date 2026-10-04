import type { ApprovedLegalDocument } from "@/lib/legal-documents";
import { InformationalPage } from "@/components/informational-page";

export function PublishedLegalDocument({ document }: { document: ApprovedLegalDocument }) {
  return <InformationalPage eyebrow="Утверждённый документ" title={document.title} description={`Версия ${document.version}`}>
    <section className="info-section"><h2>Оператор</h2><p>{document.operator.legal_name} · УНП {document.operator.unp}</p><address>{document.operator.address}</address><p>Обращения: {document.operator.contact_email}</p></section>
    <section className="info-section" aria-label="Текст документа"><div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{document.body}</div></section>
  </InformationalPage>;
}
