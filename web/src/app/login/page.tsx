import type { Metadata } from "next";
import { LoginForm } from "@/components/login-form";
import { approvedConsentVersions } from "@/lib/registration-consent";
import { safeNextPath } from "@/lib/routing";

type SearchParams = { next?: string | string[] };
export const metadata: Metadata = { title: "Вход" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [params, consentVersions] = await Promise.all([searchParams, approvedConsentVersions()]);
  const next = Array.isArray(params.next) ? params.next[0] : params.next;
  return (
    <section className="auth-page">
      <div className="auth-card">
        <p className="eyebrow">Закрытый пилот</p>
        <h1>Вход в кабинет</h1>
        <p className="muted">Используйте почту и пароль тестовой учётной записи.</p>
        <LoginForm nextPath={safeNextPath(next)} consentVersions={consentVersions} />
      </div>
    </section>
  );
}
