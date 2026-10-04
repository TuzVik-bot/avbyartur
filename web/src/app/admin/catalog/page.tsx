import Link from "next/link";
import type { Metadata } from "next";
import { AdminCatalogItem } from "@/components/admin-catalog-item";
import { AdminNav } from "@/components/admin-nav";
import { adminServerApi } from "@/lib/admin-server";
import type { AdminCatalogKind } from "@/lib/admin";
import { requireSession } from "@/lib/server";

type SearchParams = { kind?: string | string[]; q?: string | string[]; page?: string | string[] };
export const metadata: Metadata = { title: "Справочники · Администрирование" };
const kinds: { value: AdminCatalogKind; label: string }[] = [
  { value: "makes", label: "Марки" }, { value: "models", label: "Модели" }, { value: "generations", label: "Поколения" },
  { value: "body-types", label: "Типы кузова" }, { value: "body-variants", label: "Варианты кузова" },
  { value: "modifications", label: "Модификации" }, { value: "regions", label: "Регионы" }, { value: "cities", label: "Города" }
];
function first(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }
function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : 1;
}
function pageUrl(kind: AdminCatalogKind, q: string, page: number) {
  const params = new URLSearchParams({ kind });
  if (q) params.set("q", q);
  if (page > 1) params.set("page", String(page));
  return `/admin/catalog?${params.toString()}`;
}

export default async function AdminCatalogPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const session = await requireSession("/admin/catalog");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Управление справочниками доступно только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;

  const params = await searchParams;
  const rawKind = first(params.kind);
  const kind = kinds.some((entry) => entry.value === rawKind) ? rawKind as AdminCatalogKind : "makes";
  const q = (first(params.q) || "").trim().slice(0, 180);
  const page = parsePage(first(params.page));
  let result: Awaited<ReturnType<typeof adminServerApi.catalog>> | null = null;
  try { result = await adminServerApi.catalog(kind, { page, page_size: 25, q }); } catch { /* Keep an explicit API error state on the page. */ }
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Каталог и география</p><h1>Справочники</h1><p>Изменения сохраняют исходные slug и ID, требуют повторного ввода пароля и причины и попадают в версионную историю.</p></header>
    <AdminNav current="/admin/catalog" />
    <form className="admin-filter-form" method="get">
      <label className="field"><span>Справочник</span><select name="kind" defaultValue={kind}>{kinds.map((entry) => <option value={entry.value} key={entry.value}>{entry.label}</option>)}</select></label>
      <label className="field"><span>Поиск по названию</span><input type="search" name="q" maxLength={180} defaultValue={q} /></label>
      <button className="button button-secondary" type="submit">Применить</button>
    </form>
    {!result ? <p className="notice" role="alert">Не удалось загрузить справочник. Проверьте подключение к API и повторите попытку.</p> : <>
      <p className="muted">Записей: {result.total}. Страница {Math.min(page, pageCount)} из {pageCount}.</p>
      <div className="admin-catalog-list">{result.items.length ? result.items.map((item) => <AdminCatalogItem key={`${item.kind}-${item.id}`} kind={kind} initialItem={item} />) : <div className="empty-state"><h2>Записи не найдены</h2><p>Измените фильтр или выберите другой справочник.</p></div>}</div>
      {pageCount > 1 && <nav className="pagination" aria-label="Страницы справочника">{page > 1 && <Link className="button button-secondary button-small" href={pageUrl(kind, q, page - 1)}>Назад</Link>}<span>Страница {Math.min(page, pageCount)} из {pageCount}</span>{page < pageCount && <Link className="button button-secondary button-small" href={pageUrl(kind, q, page + 1)}>Дальше</Link>}</nav>}
    </>}
  </div>;
}
