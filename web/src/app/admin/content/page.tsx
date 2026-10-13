import Link from "next/link";
import { AdminNav } from "@/components/admin-nav";
import { ManagedContentEditor } from "@/components/managed-content-editor";
import { contentServerApi } from "@/lib/content-server";
import { requireSession } from "@/lib/server";

export const metadata = { title: "Материалы · Администрирование" };

export default async function AdminContentPage() {
  const session = await requireSession("/admin/content");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1></header><Link href="/account">В кабинет</Link></div>;
  let items: Awaited<ReturnType<typeof contentServerApi.listAll>> | null = null;
  try { items = await contentServerApi.listAll(); } catch { items = null; }
  return <div className="page-width"><header className="page-head"><h1>Материалы</h1></header><AdminNav current="/admin/content" /><ManagedContentEditor initialItems={items || []} initialError={!items} /></div>;
}
