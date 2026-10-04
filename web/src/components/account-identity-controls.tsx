"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { api, type AccountDeletionResult, type AuthCapabilities, type ConsentHistoryItem, type UserProfile } from "@/lib/api";

export function AccountIdentityControls({ initialProfile, initialConsents }: {
  initialProfile: UserProfile | null;
  initialConsents: ConsentHistoryItem[] | null;
}) {
  const { user, setSession } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState(initialProfile);
  const [consents, setConsents] = useState(initialConsents);
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [displayName, setDisplayName] = useState(initialProfile?.display_name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleted, setDeleted] = useState<AccountDeletionResult | null>(null);
  const [phoneChangeChallenge, setPhoneChangeChallenge] = useState<Awaited<ReturnType<typeof api.requestPhoneChange>> | null>(null);
  const [phoneChanged, setPhoneChanged] = useState(false);
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [phoneError, setPhoneError] = useState("");
  const [newPhone, setNewPhone] = useState("");

  useEffect(() => {
    let active = true;
    api.authCapabilities().then((value) => { if (active) setCapabilities(value); }).catch(() => { if (active) setCapabilities(null); });
    return () => { active = false; };
  }, []);

  async function reloadIdentity() {
    setError("");
    try {
      const [profileResult, consentResult] = await Promise.all([api.profile(), api.consents()]);
      setProfile(profileResult.profile);
      setDisplayName(profileResult.profile.display_name);
      setConsents(consentResult.items);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось загрузить профиль."); }
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const nextName = displayName.trim();
    if (nextName.length < 2 || nextName.length > 120) { setError("Имя должно содержать от 2 до 120 символов."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.updateProfile(nextName);
      setProfile(result.profile);
      setDisplayName(result.profile.display_name);
      setNotice("Профиль сохранён.");
      router.refresh();
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось сохранить профиль."); }
    finally { setBusy(false); }
  }

  async function requestVerification() {
    if (busy || !user?.email) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api.requestEmailVerification(user.email);
      setNotice("Если для этого адреса доступно подтверждение, письмо отправлено. Перейдите по ссылке из письма.");
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось запросить письмо."); }
    finally { setBusy(false); }
  }

  async function deleteAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!deleteConfirmed) { setError("Подтвердите деактивацию аккаунта."); return; }
    setBusy(true); setError("");
    try {
      const result = await api.requestAccountDeletion();
      setDeleted(result);
      setSession(null);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось выполнить запрос."); }
    finally { setBusy(false); }
  }

  async function requestPhoneChange(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phoneBusy) return;
    const phone = newPhone.trim();
    if (!phone) { setPhoneError("Укажите новый номер телефона."); return; }
    setPhoneBusy(true); setPhoneError("");
    try {
      const challenge = await api.requestPhoneChange(phone);
      setPhoneChangeChallenge(challenge);
    } catch (issue) {
      setPhoneError(issue instanceof Error ? issue.message : "Не удалось отправить коды подтверждения.");
    } finally { setPhoneBusy(false); }
  }

  async function confirmPhoneChange(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phoneBusy || !phoneChangeChallenge) return;
    const values = new FormData(event.currentTarget);
    const oldCode = String(values.get("old_code") || "").trim();
    const newCode = String(values.get("new_code") || "").trim();
    if (!/^\d{6}$/.test(oldCode) || !/^\d{6}$/.test(newCode)) {
      setPhoneError("Введите два шестизначных кода из SMS.");
      return;
    }
    setPhoneBusy(true); setPhoneError("");
    try {
      await api.confirmPhoneChange(phoneChangeChallenge.challenge_id, oldCode, newCode);
      setPhoneChanged(true);
      setPhoneChangeChallenge(null);
      setNewPhone("");
      setSession(null);
      router.replace("/login?notice=phone-changed");
      router.refresh();
    } catch (issue) {
      setPhoneError(issue instanceof Error ? issue.message : "Коды не подошли или устарели. Запросите новые.");
    } finally { setPhoneBusy(false); }
  }

  if (deleted) return <section className="account-identity-success" role="status">
    <h2>Аккаунт деактивирован</h2>
    <p>Запрос обработан. Отозвано сеансов: {deleted.revoked_sessions}. Снято с публикации объявлений: {deleted.withdrawn_listings}. История действий и согласий сохранена.</p>
    <Link className="button button-secondary" href="/">На главную</Link>
  </section>;

  if (phoneChanged) return <section className="account-identity-success" role="status">
    <h2>Номер телефона изменён</h2>
    <p>Для защиты аккаунта все активные сеансы завершены. Войдите снова с подтверждённым номером.</p>
    <Link className="button button-primary" href="/login">Ко входу</Link>
  </section>;

  return <div className="account-identity-controls">
    <section className="identity-section" aria-labelledby="profile-heading">
      <div className="section-heading"><h2 id="profile-heading">Профиль</h2></div>
      {!profile ? <div><p className="notice">Не удалось загрузить профиль.</p><button className="button button-secondary button-small" type="button" onClick={reloadIdentity}>Повторить загрузку</button></div> : <>
        <form className="identity-profile-form" onSubmit={saveProfile}>
          <label className="field"><span>Отображаемое имя</span><input name="display_name" autoComplete="name" minLength={2} maxLength={120} required value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} /></label>
          <button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить профиль"}</button>
        </form>
        <dl className="identity-contact-list">
          <div><dt>Электронная почта</dt><dd>{profile.contacts.email.masked || "Не указана"} · {profile.contacts.email.verified ? "подтверждена" : "не подтверждена"}</dd></div>
          <div><dt>Телефон</dt><dd>{profile.contacts.phone.masked || "Не указан"} · {profile.contacts.phone.verified ? "подтверждён" : "не подтверждён"}</dd></div>
        </dl>
        {capabilities?.email_verification && !profile.contacts.email.verified && user?.email && <button className="button button-secondary button-small" type="button" disabled={busy} onClick={requestVerification}>Отправить письмо для подтверждения почты</button>}
        <div className="identity-phone-change">
          <h3>Смена телефона</h3>
          {!profile.contacts.phone.verified ? <p className="notice">Для смены номера сначала подтвердите текущий телефон.</p> : !phoneChangeChallenge ? <>
            <p className="muted">Мы отправим отдельные коды на текущий и новый номера. Оба номера должны быть доступны для SMS.</p>
            <form key="phone-change-request" className="identity-phone-change-form" onSubmit={requestPhoneChange}>
              <label className="field"><span>Новый номер телефона</span><input name="new_phone" type="tel" inputMode="tel" autoComplete="tel" maxLength={40} value={newPhone} onChange={(event) => setNewPhone(event.currentTarget.value)} required /></label>
              <button className="button button-secondary button-small" type="submit" disabled={phoneBusy}>{phoneBusy ? "Отправляем коды…" : "Отправить коды"}</button>
            </form>
          </> : <>
            <p className="muted">Введите коды, отправленные на текущий номер {phoneChangeChallenge.old_phone_masked} и новый номер {phoneChangeChallenge.new_phone_masked}. Срок действия — до {Math.max(1, Math.ceil(phoneChangeChallenge.expires_in_seconds / 60))} мин.</p>
            <form key="phone-change-confirm" className="identity-phone-change-form" data-phone-change-confirm onSubmit={confirmPhoneChange}>
              <label className="field"><span>Код на текущий номер</span><input name="old_code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label>
              <label className="field"><span>Код на новый номер</span><input name="new_code" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label>
              <div className="form-actions"><button className="button button-primary button-small" type="submit" disabled={phoneBusy}>{phoneBusy ? "Проверяем…" : "Подтвердить смену"}</button><button className="button button-secondary button-small" type="button" disabled={phoneBusy} onClick={() => { setPhoneChangeChallenge(null); setPhoneError(""); }}>Отмена</button></div>
            </form>
          </>}
          {phoneError && <p className="inline-error" role="alert">{phoneError}</p>}
        </div>
      </>}
    </section>

    <section className="identity-section" aria-labelledby="consents-heading">
      <div className="section-heading"><h2 id="consents-heading">История согласий</h2></div>
      {consents === null ? <p className="muted">Не удалось загрузить историю. Обновите страницу или повторите попытку.</p> : consents.length ? <ul className="consent-history">{consents.map((item, index) => <li key={`${item.document_type}-${item.version}-${item.accepted_at}-${index}`}>
        <strong>{item.document_type}</strong><span>Версия {item.version}</span><span>{new Date(item.accepted_at).toLocaleString("ru-RU")}</span><span className="muted">Источник: {item.source}</span>
      </li>)}</ul> : <p className="muted">Сохранённых согласий нет.</p>}
    </section>

    <section className="identity-section identity-danger" aria-labelledby="delete-heading">
      <div className="section-heading"><h2 id="delete-heading">Деактивация аккаунта</h2></div>
      <p>Аккаунт будет деактивирован, активные сеансы завершатся, а ваши объявления будут сняты с публикации. История и аудит сохраняются.</p>
      <form className="account-deletion-form" onSubmit={deleteAccount}>
        <label className="check-field"><input type="checkbox" checked={deleteConfirmed} onChange={(event) => setDeleteConfirmed(event.currentTarget.checked)} /> Подтверждаю деактивацию аккаунта и снятие объявлений с публикации.</label>
        <button className="button button-danger button-small" type="submit" disabled={busy}>{busy ? "Обрабатываем…" : "Деактивировать аккаунт"}</button>
      </form>
    </section>
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
