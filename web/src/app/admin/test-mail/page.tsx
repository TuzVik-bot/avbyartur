import Link from "next/link";
import { AdminNav } from "@/components/admin-nav";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata = { title: "Тестовая почта" };
type Item = { id: string; subject: string; recipients: string[]; created_at: string };
export default async function TestMailPage({ searchParams }: { searchParams: Promise<{ message?: string }> }) {
  const session = await requireSession("/admin/test-mail");
  if (session.user.role !== "admin") return <section className="page-width"><h1>Нет доступа</h1><p>Тестовая почта доступна только администратору.</p></section>;
  const params = await searchParams;
  let items: Item[] = [], message: { subject: string; body: string } | null = null, unavailable = false;
  try {
    items = (await serverApiRequest<{items: Item[]}>("admin/test-mail/messages")).items;
    if (params.message && /^[A-Za-z0-9_-]{22,64}$/.test(params.message)) message = await serverApiRequest(`admin/test-mail/messages/${params.message}`);
  } catch { unavailable = true; }
  const code = message?.body.match(/Код:\s*([A-Za-z0-9_-]{20,200})/)?.[1];
  const target = message?.subject.includes("Восстановление") ? "/recover" : "/verify-email";
  return <section className="page-width">
    <header className="page-head"><h1>Тестовая почта</h1><p>Письма для проверки сервиса. Доставка на внешние адреса выключена.</p></header>
    <AdminNav current="/admin/test-mail" />
    <Link className="button button-secondary" href="/admin/test-mail">Обновить список</Link>
    {unavailable ? <p className="notice">Тестовый ящик недоступен или выключен.</p> : <>
      <ul>{items.map(item => <li key={item.id}><Link href={`/admin/test-mail?message=${encodeURIComponent(item.id)}`}>{item.subject}</Link> — {item.recipients.join(", ")}</li>)}</ul>
      {!items.length && <p>Писем пока нет. Запросите подтверждение почты в настройках аккаунта или восстановление пароля.</p>}
      {message && <article><h2>{message.subject}</h2><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{message.body}</pre>{code && <Link className="button button-primary" href={`${target}#token=${encodeURIComponent(code)}`}>Открыть ссылку из письма</Link>}</article>}
    </>}
  </section>;
}
