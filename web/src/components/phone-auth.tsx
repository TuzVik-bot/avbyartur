"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { api, type AuthCapabilities, type RegistrationConsentVersions } from "@/lib/api";
import { safeNextPath } from "@/lib/routing";

type PhoneMode = "login" | "register";

export function PhoneAuth({ nextPath, capabilities, loadingCapabilities, consentVersions }: { nextPath: string; capabilities: AuthCapabilities | null; loadingCapabilities: boolean; consentVersions: RegistrationConsentVersions | null }) {
  const { setSession } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<PhoneMode>("login");
  const [phone, setPhone] = useState("");
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (capabilities && !capabilities.sms_login && capabilities.sms_registration && consentVersions) setMode("register");
  }, [capabilities, consentVersions]);

  async function requestCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !capabilities) return;
    const data = new FormData(event.currentTarget);
    const nextPhone = String(data.get("phone") || "").trim();
    const displayName = String(data.get("display_name") || "").trim();
    const acceptedTerms = data.get("accept_terms") === "yes";
    const acceptedPrivacy = data.get("accept_privacy") === "yes";
    if (mode === "register" && displayName.length < 2) { setError("Укажите имя длиной не менее двух символов."); return; }
    if (mode === "register" && (!acceptedTerms || !acceptedPrivacy)) { setError("Для регистрации подтвердите согласие с документами."); return; }

    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "register" && consentVersions) await api.requestRegistrationOtp({
        phone: nextPhone, display_name: displayName, accept_terms: true, accept_privacy: true,
        terms_version: consentVersions.terms, privacy_version: consentVersions.privacy
      });
      else await api.requestLoginOtp(nextPhone);
      setPhone(nextPhone);
      setAwaitingCode(true);
      setNotice("Если номер подходит для этого способа входа, код отправлен. Проверьте SMS.");
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось запросить код. Попробуйте позже.");
    } finally { setBusy(false); }
  }

  async function verifyCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const code = String(data.get("code") || "").trim();
    if (!/^\d{6}$/.test(code)) { setError("Введите шестизначный код из SMS."); return; }
    setBusy(true);
    setError("");
    try {
      const session = await api.verifyPhoneOtp(phone, code);
      setSession(session);
      router.replace(safeNextPath(nextPath));
      router.refresh();
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Код не подошёл или истёк. Запросите новый код.");
    } finally { setBusy(false); }
  }

  if (loadingCapabilities) return <p className="muted phone-auth-state" role="status">Проверяем доступные способы входа…</p>;
  if (!capabilities) return null;
  const canLogin = capabilities.sms_login;
  const canRegister = capabilities.sms_registration && consentVersions !== null;
  const registrationBlocked = capabilities.sms_registration && !consentVersions;
  if (!canLogin && !canRegister) return registrationBlocked ? <p className="notice" role="status">Регистрация по SMS сейчас недоступна: утверждённые версии документов не опубликованы.</p> : null;

  return (
    <section className="phone-auth" aria-label="Вход по телефону">
      <div className="phone-auth-heading"><h2>{canLogin && canRegister ? "Вход по телефону" : canRegister ? "Регистрация по телефону" : "Вход по SMS"}</h2><p className="muted">Код действует ограниченное время и вводится только на этом сайте.</p></div>
      {registrationBlocked && <p className="notice" role="status">Регистрация по SMS сейчас недоступна: утверждённые версии документов не опубликованы.</p>}
      {!awaitingCode && canLogin && canRegister && <div className="phone-auth-modes" role="group" aria-label="Способ по телефону">
        <button type="button" className={mode === "login" ? "button button-secondary button-small is-selected" : "button button-secondary button-small"} aria-pressed={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Войти</button>
        <button type="button" className={mode === "register" ? "button button-secondary button-small is-selected" : "button button-secondary button-small"} aria-pressed={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Создать аккаунт</button>
      </div>}
      {!awaitingCode ? <form className="phone-auth-form" onSubmit={requestCode}>
        {mode === "register" && <label className="field"><span>Имя</span><input name="display_name" required minLength={2} maxLength={120} autoComplete="name" /></label>}
        <label className="field"><span>Номер телефона</span><input name="phone" type="tel" inputMode="tel" autoComplete="tel" minLength={7} maxLength={40} required defaultValue={phone} onChange={(event) => setPhone(event.currentTarget.value)} placeholder="+375 29 123-45-67" /></label>
        {mode === "register" && <div className="phone-auth-consents">
          <label className="check-field"><input name="accept_terms" type="checkbox" value="yes" required /> Принимаю <a href="/terms-of-use" target="_blank" rel="noreferrer">условия использования</a> версии {consentVersions!.terms}.</label>
          <label className="check-field"><input name="accept_privacy" type="checkbox" value="yes" required /> Принимаю <a href="/privacy-policy" target="_blank" rel="noreferrer">политику конфиденциальности</a> версии {consentVersions!.privacy}.</label>
        </div>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Отправляем…" : "Получить код"}</button>
      </form> : <form className="phone-auth-form" onSubmit={verifyCode}>
        <p className="muted">Номер: <strong>{phone}</strong></p>
        <label className="field"><span>Код из SMS</span><input name="code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label>
        {notice && <p className="notice" role="status">{notice}</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Проверяем…" : "Подтвердить код"}</button>
        <button className="button button-secondary" type="button" disabled={busy} onClick={() => { setAwaitingCode(false); setError(""); setNotice(""); }}>Изменить номер или запросить код заново</button>
      </form>}
    </section>
  );
}
