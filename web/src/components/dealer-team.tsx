"use client";

import { useRef, useState } from "react";
import { ApiClientError, createIdempotencyKey } from "@/lib/api";
import { dealerTeamApi, type DealerTeamMember, type DealerTeamMemberRole } from "@/lib/dealer";

const roleLabels: Record<DealerTeamMemberRole | "owner", string> = {
  owner: "Владелец",
  admin: "Администратор",
  seller: "Продавец",
  viewer: "Наблюдатель"
};

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError) {
    if (issue.code === "revision_conflict") return "Состав команды изменился. Обновите список и повторите действие.";
    if (issue.code === "active_user_not_found") return "Активный пользователь с таким ID не найден.";
    if (issue.code === "user_already_in_company") return "Пользователь уже связан с другой компанией.";
    if (issue.code === "team_member_exists") return "Пользователь уже состоит в команде.";
    if (issue.code === "inactive_user") return "Этот аккаунт неактивен и не может быть возвращён в команду.";
    if (issue.status === 401) return "Сессия закончилась. Войдите снова.";
  }
  return issue instanceof Error ? issue.message : "Не удалось выполнить действие.";
}

export function DealerTeam({ initialMembers, currentUserId }: { initialMembers: DealerTeamMember[] | null; currentUserId: string }) {
  const [members, setMembers] = useState(initialMembers);
  const [userId, setUserId] = useState("");
  const [newRole, setNewRole] = useState<DealerTeamMemberRole>("seller");
  const [draftRoles, setDraftRoles] = useState<Record<string, DealerTeamMemberRole>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const addAttempt = useRef<{ fingerprint: string; key: string } | null>(null);

  const actor = members?.find((member) => member.user_id === currentUserId && member.status === "active");
  const isOwner = actor?.role === "owner";
  const canManage = isOwner || actor?.role === "admin";

  async function reload() {
    setBusy(true);
    setError("");
    try {
      const result = await dealerTeamApi.list();
      setMembers(result.items);
      setNotice("Список команды обновлён.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function addMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManage || busy) return;
    const normalizedId = userId.trim();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(normalizedId)) {
      setError("Введите ID пользователя в формате UUID.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    const fingerprint = `${normalizedId}:${newRole}`;
    if (!addAttempt.current || addAttempt.current.fingerprint !== fingerprint) addAttempt.current = { fingerprint, key: createIdempotencyKey() };
    try {
      const result = await dealerTeamApi.add(normalizedId, newRole, addAttempt.current.key);
      addAttempt.current = null;
      setMembers((current) => current ? [...current.filter((member) => member.id !== result.member.id), result.member] : [result.member]);
      setUserId("");
      setNotice("Пользователь добавлен в команду.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function updateMember(member: DealerTeamMember, change: { role?: DealerTeamMemberRole; status?: "active" | "revoked" }) {
    if (!canManage || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await dealerTeamApi.update(member, change);
      setMembers((current) => current?.map((item) => item.id === result.member.id ? result.member : item) ?? [result.member]);
      setDraftRoles((current) => { const next = { ...current }; delete next[member.id]; return next; });
      setNotice("Изменения команды сохранены.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  if (members === null) return <section className="notice" role="alert">
    <p>Не удалось загрузить команду или у аккаунта пока нет доступа к компании.</p>
    <button className="button button-secondary button-small" type="button" disabled={busy} onClick={reload}>Повторить загрузку</button>
  </section>;

  return <div className="dealer-team">
    <section className="section" aria-labelledby="team-list-heading">
      <div className="section-heading"><div><h2 id="team-list-heading">Состав команды</h2><p className="muted">Права применяются к объявлениям компании. Изменения фиксируются в аудите.</p></div><button className="button button-secondary button-small" type="button" disabled={busy} onClick={reload}>Обновить</button></div>
      {!members.length ? <p className="muted" role="status">У компании пока нет участников.</p> : <div className="info-table-wrap"><table className="info-table"><thead><tr><th>Участник</th><th>Роль</th><th>Состояние</th>{canManage && <th>Действия</th>}</tr></thead><tbody>
        {members.map((member) => {
          const protectedRow = member.role === "owner" || (member.role === "admin" && !isOwner);
          const editable = canManage && !protectedRow;
          const selectedRole = draftRoles[member.id] ?? (member.role === "owner" ? "seller" : member.role);
          return <tr key={member.id}>
            <td><strong>{member.display_name}</strong><small>{member.email || "Почта не указана"}</small></td>
            <td>{editable ? <label className="dealer-team-role"><span className="sr-only">Роль для {member.display_name}</span><select value={selectedRole} disabled={busy} onChange={(event) => setDraftRoles((current) => ({ ...current, [member.id]: event.currentTarget.value as DealerTeamMemberRole }))}>
              <option value="seller">Продавец</option><option value="viewer">Наблюдатель</option>{isOwner && <option value="admin">Администратор</option>}
            </select></label> : roleLabels[member.role]}</td>
            <td>{member.status === "active" ? "Активен" : "Отозван"}</td>
            {canManage && <td><div className="dealer-team-actions">
              {editable && draftRoles[member.id] && draftRoles[member.id] !== member.role && <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => updateMember(member, { role: draftRoles[member.id] })}>Сохранить роль</button>}
              {editable && <button className={member.status === "active" ? "button button-danger button-small" : "button button-secondary button-small"} type="button" disabled={busy} onClick={() => updateMember(member, { status: member.status === "active" ? "revoked" : "active" })}>{member.status === "active" ? "Отозвать доступ" : "Вернуть в команду"}</button>}
              {protectedRow && <span className="muted">Управление недоступно</span>}
            </div></td>}
          </tr>;
        })}
      </tbody></table></div>}
      {!canManage && <p className="muted">У вас есть доступ к просмотру команды. Изменять её может владелец или администратор компании.</p>}
    </section>

    {canManage && <section className="section" aria-labelledby="team-add-heading">
      <div className="section-heading"><div><h2 id="team-add-heading">Добавить участника</h2><p className="muted">Укажите ID существующего активного аккаунта. Участник не сможет входить в аккаунт другого пользователя.</p></div></div>
      <form className="dealer-team-add" onSubmit={addMember}>
        <label className="field"><span>ID пользователя</span><input inputMode="text" autoComplete="off" spellCheck={false} value={userId} onChange={(event) => setUserId(event.currentTarget.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" aria-describedby="dealer-team-user-id-help" required /></label>
        <p id="dealer-team-user-id-help" className="muted">Пользователь должен иметь аккаунт и не состоять в другой компании.</p>
        <label className="field"><span>Роль</span><select value={newRole} onChange={(event) => setNewRole(event.currentTarget.value as DealerTeamMemberRole)} disabled={busy}><option value="seller">Продавец</option><option value="viewer">Наблюдатель</option>{isOwner && <option value="admin">Администратор</option>}</select></label>
        <button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Добавляем…" : "Добавить в команду"}</button>
      </form>
    </section>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
