export type ModerationRiskSignal = {
  code: string;
  severity: "low" | "medium" | "high";
  summary: string;
  related_count?: number;
};

const signalLabels: Record<string, string> = {
  duplicate_vin: "Совпадение VIN",
  repeated_phone: "Повтор телефона",
  repeated_description: "Повтор описания",
  external_link: "Внешняя ссылка",
  contact_token: "Контактные данные в тексте",
  unusually_low_price: "Цена заметно ниже похожих объявлений",
  high_submission_velocity: "Много подач за короткое время"
};

// Summaries received from the API are untrusted and may accidentally include
// raw contact or vehicle identifiers. Render only copy owned by this UI.
const signalSummaries = new Map<string, string>([
  ["duplicate_vin", "Данные VIN совпадают с другими объявлениями."],
  ["repeated_phone", "Контактный номер встречается в других объявлениях."],
  ["repeated_description", "Похожие описания встречаются в других объявлениях."],
  ["external_link", "В описании найдена внешняя ссылка."],
  ["contact_token", "В тексте описания найдены контактные данные."],
  ["unusually_low_price", "Цена ниже диапазона похожих объявлений."],
  ["high_submission_velocity", "Для аккаунта выявлено много подач за короткое время."]
]);

const severityLabels: Record<ModerationRiskSignal["severity"], string> = {
  low: "Низкая важность",
  medium: "Средняя важность",
  high: "Высокая важность"
};

function relatedCountLabel(count: number) {
  const remainder100 = count % 100;
  const remainder10 = count % 10;
  const noun = remainder100 >= 11 && remainder100 <= 14
    ? "объявлений"
    : remainder10 === 1
      ? "объявление"
      : remainder10 >= 2 && remainder10 <= 4
        ? "объявления"
        : "объявлений";

  return `Связанных ${noun}: ${count}`;
}

export function ModerationRiskSignals({ signals }: { signals?: ModerationRiskSignal[] }) {
  if (!signals?.length) return null;

  return (
    <section className="moderation-risk-signals" aria-label="Подсказки модератору">
      <h3>Сигналы для проверки</h3>
      <ul>
        {signals.map((signal, index) => (
          <li className="moderation-risk-signal" key={`${signal.code}-${index}`}>
            <div className="moderation-risk-signal-heading">
              <span className={`moderation-risk-severity moderation-risk-severity-${signal.severity}`}>
                {severityLabels[signal.severity]}
              </span>
              <strong>{signalLabels[signal.code] || "Дополнительный сигнал"}</strong>
            </div>
            <p>{signalSummaries.get(signal.code) || "Требуется дополнительная проверка."}</p>
            {typeof signal.related_count === "number" && Number.isSafeInteger(signal.related_count) && signal.related_count >= 0 && (
              <span className="moderation-risk-related-count">{relatedCountLabel(signal.related_count)}</span>
            )}
          </li>
        ))}
      </ul>
      <p className="moderation-risk-disclaimer">Подсказки для модератора, не автоматическое решение.</p>
    </section>
  );
}
