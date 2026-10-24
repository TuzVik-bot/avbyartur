import type { DealerFeedImportRow, DealerFeedImportRun } from "@/lib/dealer";
import Link from "next/link";

export type FeedImportDetail = { feed_name: string; run: DealerFeedImportRun; rows: DealerFeedImportRow[] | null };

function nextStepText(row: DealerFeedImportRow): string {
  if (row.action === "missing_paused") return "Приостановлено после подтверждения.";
  if (row.status === "unchanged") return "Без изменений; статус объявления сохранён.";
  if (row.status === "rejected") return "Отклонено; объявление не изменено.";
  if (row.status === "draft" && row.action === "created") return "Проверьте черновик и отправьте его на модерацию.";
  if (row.status === "draft") return "После обновления объявление находится в черновиках. Проверьте изменения и отправьте его на модерацию.";
  return "—";
}

const statusLabels: Record<DealerFeedImportRun["status"], string> = {
  preview: "Предпросмотр",
  succeeded: "Завершён",
  partial: "Завершён с ошибками",
  failed: "Ошибка"
};

export function FeedImportHistory({ items, selectedId, onSelect, nextCursor, loading, error, onLoadMore, onRetry, selectedRowsLoading, selectedRowsError, onRetrySelectedRows }: {
  items: FeedImportDetail[];
  selectedId: string | null;
  onSelect: (runId: string) => void;
  nextCursor: string | null;
  loading: boolean;
  error: string;
  onLoadMore: () => void;
  onRetry: () => void;
  selectedRowsLoading: boolean;
  selectedRowsError: string;
  onRetrySelectedRows: () => void;
}) {
  const selected = items.find((item) => item.run.id === selectedId) ?? null;
  return <section className="section feed-history" aria-labelledby="feed-history-heading">
    <div className="section-heading"><div><h2 id="feed-history-heading">История импортов</h2><p className="muted">Предпросмотр не меняет объявления. Новые и изменённые записи после успешного применения становятся черновиками: владелец, администратор или продавец проверяет карточку и отправляет её на модерацию. Неизменённые объявления сохраняют статус; отклонённые строки не применяются. Изменение активного объявления возвращает его в черновики и скрывает из каталога до проверки и повторной отправки.</p></div></div>
    {error && <p className="inline-error" role="alert">{error} <button className="button button-secondary button-small" type="button" onClick={onRetry}>Повторить загрузку</button></p>}
    {!items.length && loading && <p className="muted" role="status">Загружаем историю импортов…</p>}
    {!items.length && !loading && !error && <p className="muted" role="status">Импортов пока нет.</p>}
    {items.length > 0 && <ul className="feed-run-list">{items.map(({ feed_name, run }) => <li key={run.id}>
      <button className={run.id === selectedId ? "feed-run-button is-selected" : "feed-run-button"} type="button" aria-pressed={run.id === selectedId} onClick={() => onSelect(run.id)}>
        <strong>{feed_name} · {run.source_filename}</strong><span>{statusLabels[run.status]}{run.dry_run ? " · без записи" : " · применён"}</span><span>{run.applied_rows} строк · ошибок: {run.rejected_rows}</span><time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString("ru-RU")}</time>
      </button>
    </li>)}</ul>}
    {nextCursor && <button className="button button-secondary button-small" type="button" disabled={loading} onClick={onLoadMore}>{loading ? "Загружаем…" : "Загрузить ещё"}</button>}
    {selected && <div className="feed-import-detail" aria-live="polite">
      <h3>Строки: {selected.feed_name} · {selected.run.source_filename}</h3>
      <p>{selected.run.total_rows} всего · {selected.run.applied_rows} принято · {selected.run.rejected_rows} отклонено</p>
      {selected.run.error_code && <p className="inline-error">Ошибка обработки: {selected.run.error_code}</p>}
      {selectedRowsError && <p className="inline-error" role="alert">{selectedRowsError} <button className="button button-secondary button-small" type="button" onClick={onRetrySelectedRows}>Повторить загрузку строк</button></p>}
      {selectedRowsLoading && <p className="muted" role="status">Загружаем строки импорта…</p>}
      {selected.rows !== null && selected.rows.length > 0 && <div className="info-table-wrap"><table className="info-table"><thead><tr><th>Строка</th><th>ID источника</th><th>Результат</th><th>Следующий шаг</th><th>Ошибка</th></tr></thead><tbody>{selected.rows.map((row) => <tr key={row.id}>
        <td>{row.row_number}</td><td>{row.dealer_external_id || "—"}</td><td>{row.action || row.status}</td><td><p>{nextStepText(row)}</p>{row.status === "draft" && row.listing_id && <><p className="muted">Редактирование и отправка доступны владельцу, администратору или продавцу компании.</p><Link className="text-link" href={`/sell?listing=${encodeURIComponent(row.listing_id)}`} aria-label={`Открыть объявление ${row.dealer_external_id || `строка ${row.row_number}`}`}>Открыть объявление</Link></>}</td><td>{row.error_message || row.error_code || (Object.keys(row.field_errors).length ? Object.entries(row.field_errors).map(([field, message]) => `${field}: ${message}`).join("; ") : "—")}</td>
      </tr>)}</tbody></table></div>}
      {selected.rows !== null && !selected.rows.length && selected.run.rejected_rows === 0 && <p className="muted">Ошибок строк нет.</p>}
    </div>}
  </section>;
}
