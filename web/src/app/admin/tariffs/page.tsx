import Link from "next/link";
import type { Metadata } from "next";
import { AdminNav } from "@/components/admin-nav";
import { AdminTariffEditor } from "@/components/admin-tariff-editor";
import { adminTariffsServerApi } from "@/lib/admin-tariffs-server";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Тарифы · Администрирование" };

export default async function AdminTariffsPage() {
  const session = await requireSession("/admin/tariffs");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Управление тарифами доступно только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;

  let result: Awaited<ReturnType<typeof adminTariffsServerApi.list>> | null = null;
  try { result = await adminTariffsServerApi.list(); } catch { result = null; }

  return <div className="page-width">
    <header className="page-head">
      <p className="eyebrow">Платные услуги</p>
      <h1>Тарифы</h1>
      <p>Укажите только цены и длительности, утверждённые владельцем. Новые тарифы по умолчанию выключены и не добавляются автоматически.</p>
      <p className="notice" role="note">Платёжный checkout закрыт. Эта страница управляет тарифами; она не подключает провайдера оплаты.</p>
    </header>
    <AdminNav current="/admin/tariffs" />
    <AdminTariffEditor initialTariffs={result?.items || []} initialError={!result} />
  </div>;
}
