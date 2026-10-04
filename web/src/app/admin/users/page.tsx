import Link from "next/link";
import type { Metadata } from "next";
import { AdminNav } from "@/components/admin-nav";
import { AdminUserActions } from "@/components/admin-user-actions";
import { type AdminRole } from "@/lib/admin";
import { adminServerApi } from "@/lib/admin-server";
import { requireSession } from "@/lib/server";

type SearchParams = { q?: string | string[]; role?: string | string[]; status?: string | string[]; page?: string | string[]; page_size?: string | string[] };
export const metadata: Metadata = { title: "Пользователи · Администрирование" };

function first(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }
function parsePositiveInt(value: string | undefined, fallback: number) {
  if (!value || !/^[1-9]\d*$/.test(value)) return fallback;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : fallback;
}
function usersPageUrl(filters: { q?: string; role?: string; status?: string; page_size: number }, page: number) {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.role) params.set("role", filters.role);
  if (filters.status) params.set("status", filters.status);
  params.set("page_size", String(filters.page_size));
  if (page > 1) params.set("page", String(page));
  return `/admin/users?${params.toString()}`;
}

export default async function AdminUsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const session = await requireSession("/admin/users");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Управление пользователями доступно только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;

  const params = await searchParams;
  const rawRole = first(params.role);
  const role = rawRole === "user" || rawRole === "moderator" || rawRole === "admin" ? rawRole as AdminRole : undefined;
  const rawStatus = first(params.status);
  const status = rawStatus === "active" || rawStatus === "blocked" ? rawStatus : undefined;
  const q = (first(params.q) || "").trim().slice(0, 180);
  const page = parsePositiveInt(first(params.page), 1);
  const page_size = Math.min(parsePositiveInt(first(params.page_size), 25), 100);
  let result: Awaited<ReturnType<typeof adminServerApi.users>> | null = null;
  try { result = await adminServerApi.users({ page, page_size, q, role, status }); } catch { /* Keep the page available with a retryable state. */ }
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  const filters = { q, role, status, page_size };

  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Управление доступом</p><h1>Пользователи</h1><p>Найдено: {result?.total ?? "—"}. Изменения доступа требуют повторного ввода пароля и попадают в аудит.</p></header>
      <AdminNav current="/admin/users" />
      <form className="admin-filter-form" method="get">
        <label className="field"><span>Поиск по имени или почте</span><input name="q" type="search" maxLength={180} defaultValue={q} /></label>
        <label className="field"><span>Роль</span><select name="role" defaultValue={role || ""}><option value="">Все роли</option><option value="user">Пользователь</option><option value="moderator">Модератор</option><option value="admin">Администратор</option></select></label>
        <label className="field"><span>Статус</span><select name="status" defaultValue={status || ""}><option value="">Все статусы</option><option value="active">Активен</option><option value="blocked">Заблокирован</option></select></label>
        <input type="hidden" name="page_size" value={page_size} />
        <button className="button button-secondary" type="submit">Применить</button>
      </form>
      {!result ? <p className="notice" role="alert">Не удалось загрузить список пользователей. Проверьте доступ к API и повторите попытку.</p> : <>
        <div className="account-list admin-user-list">{result.items.length ? result.items.map((user) => <article className="account-list-item admin-user-item" key={user.id}>
          <div><h2>{user.display_name || "Без имени"}</h2><p>{user.email || "Почта не указана"}</p><p className="muted">{user.id} · {new Date(user.created_at).toLocaleDateString("ru-RU")} · {user.role} · {user.status}</p></div>
          <AdminUserActions user={user} currentUserId={session.user.id} />
        </article>) : <div className="empty-state"><h2>Пользователи не найдены</h2><p>Измените фильтры поиска.</p></div>}</div>
        {pageCount > 1 && <nav className="pagination" aria-label="Страницы пользователей">
          {page > 1 && <Link className="button button-secondary button-small" href={usersPageUrl(filters, page - 1)}>Назад</Link>}
          <span>Страница {Math.min(page, pageCount)} из {pageCount}</span>
          {page < pageCount && <Link className="button button-secondary button-small" href={usersPageUrl(filters, page + 1)}>Дальше</Link>}
        </nav>}
      </>}
    </div>
  );
}
