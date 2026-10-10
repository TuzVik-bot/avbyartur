"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AuthCapabilities } from "@/lib/api";
import { useUrlFragmentToken } from "@/lib/url-fragment";

export function PasswordRecoveryForm({ token }: { token?: string }) {
  const fragmentToken = useUrlFragmentToken();
  const actionToken = token || fragmentToken;
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.authCapabilities().then((result) => { if (active) setCapabilities(result); })
      .catch(() => { if (active) setCapabilities(null); })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, []);

  async function request(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const email = String(new FormData(event.currentTarget).get("email") || "").trim();
    setBusy(true); setError(""); setNotice("");
    try {
      await api.requestPasswordRecovery(email);
      setNotice("Если для этого адреса доступно восстановление, письмо со ссылкой отправлено.");
    } catch {
      setError("Не удалось запросить восстановление. Попробуйте позже.");
    } finally { setBusy(false); }
  }

  async function confirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !actionToken) return;
    const data = new FormData(event.currentTarget);
    const password = String(data.get("new_password") || "");
    const confirmation = String(data.get("confirm_password") || "");
    if (!password) { setError("Введите новый пароль."); return; }
    if (password !== confirmation) { setError("Пароли не совпадают."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      await api.confirmPasswordRecovery(actionToken, password);
      setNotice("Пароль изменён. Теперь войдите с новым паролем.");
    } catch {
      setError("Ссылка недействительна или срок её действия истёк. Запросите восстановление заново.");
    } finally { setBusy(false); }
  }

  if (checking) return <p className="muted" role="status">Проверяем доступность восстановления…</p>;
  if (!capabilities?.password_recovery) return <div><p className="notice" role="status">Восстановление по почте сейчас недоступно. Обратитесь к администратору пилота.</p><Link className="text-link" href="/login">Вернуться ко входу</Link></div>;

  return <>
    {capabilities.test_mail && <p className="notice">Тестовый режим: письма поступают в защищённый ящик администратора, а не на внешнюю почту. Для восстановления адрес должен быть предварительно подтверждён.</p>}
    {actionToken ? <form onSubmit={confirm}>
      <label className="field"><span>Новый пароль</span><input name="new_password" type="password" autoComplete="new-password" maxLength={256} required /></label>
      <label className="field"><span>Повторите новый пароль</span><input name="confirm_password" type="password" autoComplete="new-password" maxLength={256} required /></label>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Изменить пароль"}</button>
    </form> : <form onSubmit={request}>
      <label className="field"><span>Электронная почта</span><input name="email" type="email" autoComplete="email" maxLength={254} required /></label>
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Отправляем…" : "Отправить ссылку"}</button>
    </form>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {notice.includes("Пароль изменён") ? <Link className="button button-secondary" href="/login">Ко входу</Link> : <Link className="text-link" href="/login">Вернуться ко входу</Link>}
  </>;
}
