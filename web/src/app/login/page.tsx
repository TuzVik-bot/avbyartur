import type { Metadata } from "next";
import Image from "next/image";
import { LoginForm } from "@/components/login-form";
import { contentServerApi } from "@/lib/content-server";
import type { RegistrationConsentVersions } from "@/lib/api";
import { safeNextPath } from "@/lib/routing";

type SearchParams = { next?: string | string[] };
export const metadata: Metadata = { title: "Вход" };

async function approvedConsentVersions(): Promise<RegistrationConsentVersions | null> {
  try {
    const [terms, privacy] = await Promise.all([
      contentServerApi.public("legal_document", "terms_of_use"),
      contentServerApi.public("legal_document", "privacy_policy")
    ]);
    const termsPayload = terms.content.payload;
    const privacyPayload = privacy.content.payload;
    const termsVersion = typeof termsPayload.document_version === "string" ? termsPayload.document_version : "";
    const privacyVersion = typeof privacyPayload.document_version === "string" ? privacyPayload.document_version : "";
    if (terms.content.status !== "published" || privacy.content.status !== "published" ||
      termsPayload.approved !== true || privacyPayload.approved !== true ||
      !/^[A-Za-z0-9_.-]{1,80}$/.test(termsVersion) || !/^[A-Za-z0-9_.-]{1,80}$/.test(privacyVersion)) return null;
    return { terms: termsVersion, privacy: privacyVersion };
  } catch {
    return null;
  }
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [params, consentVersions] = await Promise.all([searchParams, approvedConsentVersions()]);
  const next = Array.isArray(params.next) ? params.next[0] : params.next;
  return (
    <section className="auth-page">
      <div className="auth-visual"><Image src="/design/sell.webp" alt="Ключи от автомобиля на фоне серебристого седана" width={1200} height={800} sizes="(max-width: 640px) 100vw, 50vw" /></div>
      <div className="auth-card">
        <p className="eyebrow">Закрытый пилот</p>
        <h1>Вход в кабинет</h1>
        <p className="muted">Используйте почту и пароль тестовой учётной записи.</p>
        <LoginForm nextPath={safeNextPath(next)} consentVersions={consentVersions} />
      </div>
    </section>
  );
}
