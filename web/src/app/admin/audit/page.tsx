import Link from "next/link";
import type { Metadata } from "next";
import { AdminNav } from "@/components/admin-nav";
import { adminServerApi } from "@/lib/admin-server";
import { requireSession } from "@/lib/server";

type SearchParams = { entity_type?: string | string[]; entity_id?: string | string[]; page?: string | string[] };
export const metadata: Metadata = { title: "Аудит · Администрирование" };

function first(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }
function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : 1;
}
function auditPageUrl(filters: { entity_type?: string; entity_id?: string }, page: number) {
  const params = new URLSearchParams();
  if (filters.entity_type) params.set("entity_type", filters.entity_type);
  if (filters.entity_id) params.set("entity_id", filters.entity_id);
  if (page > 1) params.set("page", String(page));
  return `/admin/audit${params.size ? `?${params.toString()}` : ""}`;
}
function formatDetails(details: Record<string, unknown>, entityType: string) {
  const safeKeys = new Set(["reason", "revision", "expected_revision", "from_role", "to_role", "from_status", "to_status", "from_revision", "to_revision", "changed", "count", "format_version"]);
  const parts = Object.entries(details).filter(([key, value]) => safeKeys.has(key) && (["string", "number", "boolean"].includes(typeof value) || value === null))
    .map(([key, value]) => `${key}: ${value === null ? "—" : String(value)}`);
  if (entityType === "billing_tariff") {
    const labels: Record<string, string> = { code: "Код", service_code: "Услуга", name: "Название", amount: "Цена", currency: "Валюта", duration_days: "Дней", listing_quota: "Лимит объявлений", status: "Статус" };
    for (const [field, heading] of [["before", "До"], ["after", "После"]]) {
      const snapshot = details[field];
      if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) continue;
      const values = Object.entries(snapshot).filter(([key, value]) => key in labels && (["string", "number", "boolean"].includes(typeof value) || value === null))
        .map(([key, value]) => `${labels[key]}: ${value === null ? "—" : String(value)}`);
      if (values.length) parts.push(`${heading}: ${values.join(", ")}`);
    }
  }
  return parts.join(" · ");
}

export default async function AdminAuditPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const session = await requireSession("/admin/audit");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Журнал действий доступен только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;

  const params = await searchParams;
  const entity_type = (first(params.entity_type) || "").trim().slice(0, 40) || undefined;
  const entity_id = (first(params.entity_id) || "").trim().slice(0, 36) || undefined;
  const page = parsePage(first(params.page));
  let result: Awaited<ReturnType<typeof adminServerApi.audit>> | null = null;
  try { result = await adminServerApi.audit({ page, page_size: 25, entity_type, entity_id }); } catch { /* Keep the filter view and provide a clear recovery state. */ }
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  const filters = { entity_type, entity_id };

  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Контроль действий</p><h1>Журнал аудита</h1><p>Записи об административных изменениях и системных событиях. Секреты и учётные данные не отображаются.</p></header>
      <AdminNav current="/admin/audit" />
      <form className="admin-filter-form" method="get">
        <label className="field"><span>Тип объекта</span><input name="entity_type" maxLength={40} defaultValue={entity_type} placeholder="user" /></label>
        <label className="field"><span>ID объекта</span><input name="entity_id" maxLength={36} defaultValue={entity_id} /></label>
        <button className="button button-secondary" type="submit">Применить</button>
      </form>
      {!result ? <p className="notice" role="alert">Не удалось загрузить журнал аудита. Проверьте доступ к API и повторите попытку.</p> : <>
        <p className="muted">Записей: {result.total}</p>
        <div className="account-list">{result.items.length ? result.items.map((event) => <article className="account-list-item admin-audit-item" key={event.id}>
          <div><h2>{event.action}</h2><p>{event.entity_type} · {event.entity_id}</p><p className="muted">Инициатор: {event.actor_id} · <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString("ru-RU")}</time></p>
          {formatDetails(event.details, event.entity_type) && <p className="admin-audit-details">{formatDetails(event.details, event.entity_type)}</p>}</div>
        </article>) : <div className="empty-state"><h2>Записей нет</h2><p>Для выбранных фильтров событий не найдено.</p></div>}</div>
        {pageCount > 1 && <nav className="pagination" aria-label="Страницы журнала">
          {page > 1 && <Link className="button button-secondary button-small" href={auditPageUrl(filters, page - 1)}>Назад</Link>}
          <span>Страница {Math.min(page, pageCount)} из {pageCount}</span>
          {page < pageCount && <Link className="button button-secondary button-small" href={auditPageUrl(filters, page + 1)}>Дальше</Link>}
        </nav>}
      </>}
    </div>
  );
}
