import type { Metadata } from "next";
import { RegisterForm } from "@/components/register-form";
import { approvedConsentVersions } from "@/lib/registration-consent";
import { safeNextPath } from "@/lib/routing";

type SearchParams = { next?: string | string[] };
export const metadata: Metadata = { title: "Регистрация", robots: { index: false, follow: false } };

export default async function RegisterPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [params, consentVersions] = await Promise.all([searchParams, approvedConsentVersions()]);
  const next = Array.isArray(params.next) ? params.next[0] : params.next;
  return (
    <section className="auth-page">
      <div className="auth-card">
        <p className="eyebrow">Новый аккаунт</p>
        <h1>Регистрация</h1>
        <p className="muted">Укажите почту и придумайте пароль. Войти можно будет сразу после регистрации.</p>
        <RegisterForm nextPath={safeNextPath(next)} consentVersions={consentVersions} />
      </div>
    </section>
  );
}
