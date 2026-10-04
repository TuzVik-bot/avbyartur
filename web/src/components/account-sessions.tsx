"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api";

export type AccountSession = {
  id: string;
  created_at: string;
  is_current: boolean;
};

export type AccountSessionList = {
  items: AccountSession[];
};

type SessionManagementProps = {
  initialSessions: AccountSession[] | null;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-BY", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Minsk"
  }).format(new Date(value));
}

function issueMessage(issue: unknown, fallback: string) {
  return issue instanceof Error && issue.message ? issue.message : fallback;
}

export function AccountSessions({ initialSessions }: SessionManagementProps) {
  const [sessions, setSessions] = useState<AccountSession[] | null>(initialSessions);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const router = useRouter();
  const { setSession } = useAuth();

  async function reload() {
    setBusy("reload");
    setError("");
    setSuccess("");
    try {
      const result = await apiRequest<AccountSessionList>("me/sessions");
      setSessions(result.items);
    } catch (issue) {
      setError(issueMessage(issue, "Не удалось загрузить сеансы. Повторите попытку."));
    } finally {
      setBusy(null);
    }
  }

  async function revoke(session: AccountSession) {
    setBusy("session:" + session.id);
    setError("");
    setSuccess("");
    try {
      await apiRequest<{ ok: true }>("me/sessions/" + encodeURIComponent(session.id), { method: "DELETE" });
      if (session.is_current) {
        setSession(null);
        router.replace("/login?next=%2Faccount%2Fsettings");
        router.refresh();
        return;
      }
      setSessions((items) => items?.filter((item) => item.id !== session.id) ?? []);
      setSuccess("Сеанс завершён.");
    } catch (issue) {
      setError(issueMessage(issue, "Не удалось завершить сеанс. Повторите попытку."));
    } finally {
      setBusy(null);
    }
  }

  async function revokeOthers() {
    setBusy("others");
    setError("");
    setSuccess("");
    try {
      const result = await apiRequest<{ revoked_count: number }>("me/sessions/revoke-others", { method: "POST", body: JSON.stringify({}) });
      setSessions((items) => items?.filter((item) => item.is_current) ?? []);
      setSuccess(result.revoked_count > 0
        ? "Остальные сеансы завершены. Этот сеанс остался активным."
        : "Других активных сеансов нет.");
    } catch (issue) {
      setError(issueMessage(issue, "Не удалось завершить остальные сеансы. Повторите попытку."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="form-section" aria-labelledby="account-sessions-title" aria-busy={busy !== null}>
      <div className="company-form-heading">
        <div>
          <h2 id="account-sessions-title">Активные сеансы</h2>
          <p>Здесь можно проверить входы в аккаунт и завершить ненужные сеансы.</p>
        </div>
        {sessions && sessions.some((session) => !session.is_current) && (
          <button className="button button-danger button-small" type="button" disabled={busy !== null} onClick={() => void revokeOthers()}>
            <ShieldCheck size={15} /> {busy === "others" ? "Завершаем…" : "Завершить остальные"}
          </button>
        )}
      </div>

      {error && <p className="notice" role="alert">{error}</p>}
      {success && <p className="inline-success" role="status">{success}</p>}

      {sessions === null ? (
        <div className="empty-state" role="status">
          <p>Не удалось загрузить активные сеансы.</p>
          <button className="button button-secondary" type="button" disabled={busy !== null} onClick={() => void reload()}>
            <RefreshCw size={15} /> {busy === "reload" ? "Загружаем…" : "Повторить"}
          </button>
        </div>
      ) : sessions.length === 0 ? (
        <div className="empty-state"><p>Активных сеансов нет.</p></div>
      ) : (
        <ul className="account-list" aria-label="Список активных сеансов" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {sessions.map((session, index) => (
            <li className="account-list-item" key={session.id}>
              <div>
                <h3>{session.is_current ? "Этот сеанс" : "Другой сеанс"}{session.is_current && <span className="status-pill status-active">Текущий</span>}</h3>
                <p className="muted">Начат {formatDate(session.created_at)}</p>
              </div>
              <div className="account-item-actions">
                <button
                  className="button button-secondary button-small"
                  type="button"
                  aria-label={`Завершить ${session.is_current ? "текущий сеанс" : "другой сеанс"} №${index + 1}, начатый ${formatDate(session.created_at)}`}
                  disabled={busy !== null}
                  onClick={() => void revoke(session)}
                >
                  <XCircle size={15} /> {busy === "session:" + session.id ? "Завершаем…" : session.is_current ? "Завершить этот сеанс" : "Завершить"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
