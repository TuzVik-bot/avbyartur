import type { Metadata } from "next";
import Image from "next/image";
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
      <div className="auth-visual"><Image src="/design/sell.webp" alt="Ключи от автомобиля на фоне серебристого седана" width={1200} height={800} sizes="(max-width: 640px) 100vw, 50vw" /></div>
      <div className="auth-card">
        <p className="eyebrow">Закрытый пилот</p>
        <h1>Вход в кабинет</h1>
        <p className="muted">Войдите по почте и паролю или создайте аккаунт, если регистрация доступна.</p>
        <LoginForm nextPath={safeNextPath(next)} consentVersions={consentVersions} />
      </div>
    </section>
  );
}
