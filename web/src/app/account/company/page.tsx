import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { CompanyForm } from "@/components/company-form";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Компания" };

export default async function AccountCompanyPage() {
  const session = await requireSession("/account/company");
  let company = null;
  let failed = false;
  try { company = (await serverApi.company()).company; } catch { failed = true; }
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Компания</h1><p>Создайте профиль компании, дождитесь проверки и публикуйте объявления от её имени.</p></header>
      <AccountNav current="/account/company" />
      {failed ? <div className="notice" role="alert"><p>Не удалось загрузить сведения о компании.</p><Link className="button button-secondary button-small" href="/account/company?retry=1">Повторить загрузку</Link></div> : <CompanyForm initialCompany={company} companyRole={session.user.company_role} />}
    </div>
  );
}
