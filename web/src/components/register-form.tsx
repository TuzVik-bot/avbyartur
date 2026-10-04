"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError, type AuthCapabilities, type RegistrationConsentVersions } from "@/lib/api";
import { safeNextPath } from "@/lib/routing";

const MIN_PASSWORD_LENGTH = 12;

function registrationError(issue: unknown): string {
  if (!(issue instanceof ApiClientError)) return issue instanceof Error ? issue.message : "Не удалось зарегистрироваться. Повторите попытку.";
  if (issue.code === "email_taken") return "Аккаунт с этой почтой уже есть. Войдите или восстановите пароль.";
  if (issue.code === "consent_version_mismatch") return "Документы обновились. Обновите страницу и подтвердите согласие заново.";
  if (issue.status === 429) return "Слишком много попыток. Подождите и попробуйте снова.";
  if (issue.status === 422) return "Проверьте почту, имя и пароль.";
  if (issue.status === 404 || issue.status === 503) return "Регистрация сейчас недоступна.";
  return "Не удалось зарегистрироваться. Повторите попытку.";
}

export function RegisterForm({ nextPath, consentVersions }: { nextPath: string; consentVersions: RegistrationConsentVersions | null }) {
  const { setSession } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [capabilitiesLoaded, setCapabilitiesLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    api.authCapabilities().then((result) => { if (active) setCapabilities(result); })
      .catch(() => { if (active) setCapabilities(null); })
      .finally(() => { if (active) setCapabilitiesLoaded(true); });
    return () => { active = false; };
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !consentVersions) return;
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") || "").trim();
    const displayName = String(data.get("display_name") || "").trim();
    const password = String(data.get("password") || "");
    const passwordRepeat = String(data.get("password_repeat") || "");
    if (displayName.length < 2) { setError("Укажите имя длиной не менее двух символов."); return; }
    if (password.length < MIN_PASSWORD_LENGTH) { setError(`Пароль должен быть не короче ${MIN_PASSWORD_LENGTH} символов.`); return; }
    if (password !== passwordRepeat) { setError("Пароли не совпадают."); return; }
    if (data.get("accept_terms") !== "yes" || data.get("accept_privacy") !== "yes") { setError("Для регистрации подтвердите согласие с документами."); return; }

    setBusy(true);
    setError("");
    try {
      const session = await api.register({
        email, password, display_name: displayName, accept_terms: true, accept_privacy: true,
        terms_version: consentVersions.terms, privacy_version: consentVersions.privacy
      });
      setSession(session);
      router.replace(safeNextPath(nextPath));
      router.refresh();
    } catch (issue) {
      setError(registrationError(issue));
    } finally {
      setBusy(false);
    }
  }

  const loginLink = <p className="login-recovery-link">Уже есть аккаунт? <Link className="text-link" href="/login">Войти</Link></p>;
  if (!capabilitiesLoaded) return <p className="muted" role="status">Проверяем, доступна ли регистрация…</p>;
  if (!capabilities?.email_registration) return <><p className="notice" role="status">Регистрация сейчас закрыта. Доступ выдаёт администратор.</p>{loginLink}</>;
  if (!consentVersions) return <><p className="notice" role="status">Регистрация сейчас недоступна: утверждённые версии документов не опубликованы.</p>{loginLink}</>;

  return <>
    <form onSubmit={submit}>
      <label className="field"><span>Имя</span><input name="display_name" required minLength={2} maxLength={120} autoComplete="name" /></label>
      <label className="field"><span>Электронная почта</span><input name="email" type="email" autoComplete="email" required maxLength={254} /></label>
      <label className="field"><span>Пароль</span><input name="password" type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH} maxLength={256} /></label>
      <label className="field"><span>Повторите пароль</span><input name="password_repeat" type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH} maxLength={256} /></label>
      <p className="muted login-note">Не короче {MIN_PASSWORD_LENGTH} символов.</p>
      <div className="phone-auth-consents">
        <label className="check-field"><input name="accept_terms" type="checkbox" value="yes" required /> Принимаю <a href="/terms-of-use" target="_blank" rel="noreferrer">условия использования</a> версии {consentVersions.terms}.</label>
        <label className="check-field"><input name="accept_privacy" type="checkbox" value="yes" required /> Принимаю <a href="/privacy-policy" target="_blank" rel="noreferrer">политику конфиденциальности</a> версии {consentVersions.privacy}.</label>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Создаём аккаунт…" : <><UserPlus size={17} /> Зарегистрироваться</>}</button>
    </form>
    {loginLink}
  </>;
}
