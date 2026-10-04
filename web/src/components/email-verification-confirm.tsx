"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useUrlFragmentToken } from "@/lib/url-fragment";

export function EmailVerificationConfirm({ token }: { token?: string }) {
  const fragmentToken = useUrlFragmentToken();
  const actionToken = token || fragmentToken;
  const [busy, setBusy] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !actionToken) return;
    setBusy(true); setError("");
    try {
      await api.confirmEmailVerification(actionToken);
      setVerified(true);
    } catch {
      setError("Ссылка недействительна или срок её действия истёк. Запросите письмо заново в настройках аккаунта.");
    } finally { setBusy(false); }
  }

  if (verified) return <div><p className="notice" role="status">Электронная почта подтверждена.</p><Link className="button button-secondary" href="/account/settings">Открыть профиль</Link></div>;
  if (!actionToken) return <div><p className="notice" role="alert">В ссылке нет кода подтверждения.</p><Link className="text-link" href="/login">Ко входу</Link></div>;
  return <form onSubmit={submit}>
    <p className="muted">Нажмите кнопку, чтобы подтвердить адрес электронной почты.</p>
    <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Подтверждаем…" : "Подтвердить почту"}</button>
    {error && <p className="inline-error" role="alert">{error}</p>}
  </form>;
}
