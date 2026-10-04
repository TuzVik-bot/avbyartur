import type { Metadata } from "next";
import { EmailVerificationConfirm } from "@/components/email-verification-confirm";

type SearchParams = { token?: string | string[] };
export const metadata: Metadata = { title: "Подтверждение почты", robots: { index: false, follow: false } };

export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const rawToken = Array.isArray(params.token) ? params.token[0] : params.token;
  const token = rawToken?.trim().slice(0, 2048);
  return <section className="auth-page"><div className="auth-card">
    <p className="eyebrow">Безопасность аккаунта</p><h1>Подтверждение почты</h1>
    <EmailVerificationConfirm token={token} />
  </div></section>;
}
