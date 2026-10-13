"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError, type AuthCapabilities, type RegistrationConsentVersions } from "@/lib/api";
import { safeNextPath } from "@/lib/routing";
import { PhoneAuth } from "@/components/phone-auth";

export function LoginForm({ nextPath, consentVersions = null }: { nextPath: string; consentVersions?: RegistrationConsentVersions | null }) {
  const { setSession } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [capabilitiesLoaded, setCapabilitiesLoaded] = useState(false);
  const [registering, setRegistering] = useState(false);
  const emailConsentVersions = capabilities?.email_registration_pilot
    ? { terms: "pilot-email-terms-2026-10-05-v2", privacy: "pilot-email-privacy-2026-10-05-v2" } : consentVersions;
  const canRegister = Boolean(capabilities?.email_registration && emailConsentVersions);

  useEffect(() => {
    let active = true;
    setHydrated(true);
    api.authCapabilities().then((result) => { if (active) setCapabilities(result); })
      .catch(() => { if (active) setCapabilities(null); })
      .finally(() => { if (active) setCapabilitiesLoaded(true); });
    return () => { active = false; };
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    try {
      let session;
      if (registering) {
        if (!canRegister || !emailConsentVersions) throw new Error("Регистрация сейчас недоступна.");
        if (password !== String(data.get("password_confirm") || "")) throw new Error("Пароли не совпадают.");
        if (!data.get("accept_terms") || !data.get("accept_privacy")) throw new Error("Подтвердите согласие с документами.");
        session = await api.registerEmail({ email, password, display_name: String(data.get("display_name") || "").trim(),
          accept_terms: true, accept_privacy: true, terms_version: emailConsentVersions.terms, privacy_version: emailConsentVersions.privacy });
      } else session = await api.login(email, password);
      setSession(session);
      router.replace(safeNextPath(nextPath));
      router.refresh();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 429) setError("Слишком много попыток. Подождите и попробуйте снова.");
      else if (registering && issue instanceof ApiClientError && issue.status === 409) setError(issue.code === "consent_version_mismatch" ? "Обновите страницу: документы изменились." : "Эта почта уже используется. Попробуйте войти.");
      else if (issue instanceof ApiClientError && (issue.status === 401 || issue.status === 422)) setError("Проверьте адрес почты и пароль.");
      else setError(issue instanceof Error ? issue.message : "Не удалось войти. Повторите попытку.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    {canRegister && <div className="phone-auth-tabs">
      <button className="button button-secondary button-small" type="button" disabled={busy} aria-pressed={!registering} onClick={() => { setRegistering(false); setError(""); }}>Войти</button>
      <button className="button button-secondary button-small" type="button" disabled={busy} aria-pressed={registering} onClick={() => { setRegistering(true); setError(""); }}>Создать аккаунт</button>
    </div>}
    <form method="post" onSubmit={submit}>
      {registering && <label className="field"><span>Имя</span><input name="display_name" autoComplete="name" required minLength={2} maxLength={120} /></label>}
      <label className="field"><span>Электронная почта</span><input name="email" type="email" autoComplete="username" required maxLength={254} /></label>
      <label className="field"><span>Пароль</span><input name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 10 : undefined} maxLength={256} required /></label>
      {registering && <>
        <label className="field"><span>Повторите пароль</span><input name="password_confirm" type="password" autoComplete="new-password" required maxLength={256} /></label>
        <p className="muted">Не менее 10 символов. {capabilities?.test_mail ? "Письма для подтверждения и восстановления поступают в тестовый ящик администратора." : capabilities?.email_verification ? "Подтвердите почту в настройках аккаунта после регистрации." : "Подтверждение почты и восстановление пароля по письму пока недоступны."}</p>
        <p className="muted">{capabilities?.email_registration_pilot ? "Сервис работает в тестовом режиме. Реквизиты оператора ещё не опубликованы. Не размещайте чувствительные данные." : ""}</p>
        <label className="checkbox-field"><input name="accept_terms" type="checkbox" required /> Я принимаю <Link href={capabilities?.email_registration_pilot ? "/registration-terms" : "/terms-of-use"} target="_blank">условия использования</Link></label>
        <label className="checkbox-field"><input name="accept_privacy" type="checkbox" required /> Я согласен с <Link href={capabilities?.email_registration_pilot ? "/registration-privacy" : "/privacy-policy"} target="_blank">политикой обработки данных</Link></label>
      </>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      <button className="button button-primary" type="submit" disabled={busy || !hydrated}>{busy ? (registering ? "Создаём аккаунт…" : "Входим…") : <><LogIn size={17} /> {registering ? "Зарегистрироваться" : "Войти"}</>}</button>
      {!canRegister && <p className="muted login-note">Самостоятельная регистрация пока недоступна.</p>}
    </form>
    {capabilities?.password_recovery && <p className="login-recovery-link"><Link className="text-link" href="/recover">Не помню пароль</Link></p>}
    <PhoneAuth nextPath={nextPath} capabilities={capabilities} loadingCapabilities={!capabilitiesLoaded} consentVersions={consentVersions} />
  </>;
}
