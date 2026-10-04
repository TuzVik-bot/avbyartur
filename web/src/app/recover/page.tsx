import type { Metadata } from "next";
import { PasswordRecoveryForm } from "@/components/password-recovery-form";

type SearchParams = { token?: string | string[] };
export const metadata: Metadata = { title: "Восстановление пароля", robots: { index: false, follow: false } };

export default async function PasswordRecoveryPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const rawToken = Array.isArray(params.token) ? params.token[0] : params.token;
  const token = rawToken?.trim().slice(0, 2048);
  return <section className="auth-page"><div className="auth-card">
    <p className="eyebrow">Доступ к аккаунту</p><h1>{token ? "Новый пароль" : "Восстановить пароль"}</h1>
    <p className="muted">Откройте ссылку из письма, чтобы задать новый пароль, или запросите письмо повторно.</p>
    <PasswordRecoveryForm token={token} />
  </div></section>;
}
