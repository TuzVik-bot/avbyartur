"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { KeyRound, LogIn } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError, type AuthCapabilities, type RegistrationConsentVersions } from "@/lib/api";
import { safeNextPath } from "@/lib/routing";
import { PhoneAuth } from "@/components/phone-auth";

export function LoginForm({ nextPath, consentVersions = null }: { nextPath: string; consentVersions?: RegistrationConsentVersions | null }) {
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
    setError("");
    setBusy(true);
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    try {
      const session = await api.login(email, password);
      setSession(session);
      router.replace(safeNextPath(nextPath));
      router.refresh();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 429) setError("Слишком много попыток. Подождите и попробуйте снова.");
      else if (issue instanceof ApiClientError && (issue.status === 401 || issue.status === 422)) setError("Проверьте адрес почты и пароль.");
      else setError(issue instanceof Error ? issue.message : "Не удалось войти. Повторите попытку.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <form onSubmit={submit}>
      <label className="field"><span>Электронная почта</span><input name="email" type="email" autoComplete="username" required maxLength={254} /></label>
      <label className="field"><span>Пароль</span><input name="password" type="password" autoComplete="current-password" required /></label>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Входим…" : <><LogIn size={17} /> Войти</>}</button>
      <p className="muted login-note"><KeyRound size={15} /> Доступ выдаётся администратором закрытого пилота.</p>
    </form>
    {capabilities?.password_recovery && <p className="login-recovery-link"><Link className="text-link" href="/recover">Не помню пароль</Link></p>}
    <PhoneAuth nextPath={nextPath} capabilities={capabilities} loadingCapabilities={!capabilitiesLoaded} consentVersions={consentVersions} />
  </>;
}
