"use client";

import Link from "next/link";
import { ArrowRight, Clock3, RefreshCw, Save, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { api, ApiClientError } from "@/lib/api";
import type { Company, User } from "@/lib/types";

type CompanyRole = NonNullable<User["company_role"]>;
type CompanyHours = NonNullable<Company["business_hours"]>;
type CompanyHourDay = keyof CompanyHours;
type CompanyFields = Pick<Company, "name" | "unp" | "address" | "phone" | "business_hours">;
type FormError = { message: string; fieldErrors: Record<string, string>; canRefresh?: boolean };

const companyDays: { key: CompanyHourDay; label: string }[] = [
  { key: "mon", label: "Понедельник" }, { key: "tue", label: "Вторник" }, { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" }, { key: "fri", label: "Пятница" }, { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" }
];

const companyRoleLabels: Record<CompanyRole, string> = {
  owner: "Владелец", admin: "Администратор", seller: "Продавец", viewer: "Наблюдатель"
};

function emptyBusinessHours(): CompanyHours {
  return {
    mon: { closed: true }, tue: { closed: true }, wed: { closed: true }, thu: { closed: true },
    fri: { closed: true }, sat: { closed: true }, sun: { closed: true }
  };
}

const statusCopy: Record<Company["status"], { label: string; message: string }> = {
  pending: {
    label: "На проверке",
    message: "Заявка сохранена. Модератор проверит реквизиты и контакты. До решения компания не показывается в публичном каталоге."
  },
  approved: {
    label: "Допущена к пилоту",
    message: "Компания допущена к пилоту. Её активные объявления будут доступны на публичной странице компании."
  },
  rejected: {
    label: "Нужно исправить",
    message: "Модератор вернул заявку на доработку. Исправьте поля ниже и отправьте сведения повторно."
  },
  blocked: {
    label: "Доступ заблокирован",
    message: "Редактирование отключено. Обратитесь к модератору, если считаете блокировку ошибочной."
  }
};

const fieldLabels: Record<string, string> = {
  name: "Название компании",
  unp: "УНП",
  address: "Юридический адрес",
  phone: "Телефон компании",
  expected_revision: "Версия сведений"
};

function fieldMessage(field: string, message: string) {
  const hourField = /^business_hours\.(mon|tue|wed|thu|fri|sat|sun)\.(open|close)$/.exec(field);
  if (hourField) {
    const dayLabel = companyDays.find((day) => day.key === hourField[1])?.label || hourField[1];
    return `${dayLabel}, ${hourField[2] === "open" ? "открытие" : "закрытие"}: ${message}`;
  }
  if (field === "business_hours") return `Режим работы: ${message}`;
  return `${fieldLabels[field] || field}: ${message}`;
}

function describeError(issue: unknown): FormError {
  if (issue instanceof ApiClientError) {
    if (issue.code === "revision_conflict") {
      return {
        message: "Сведения компании изменились в другой вкладке или у другого сотрудника. Загрузите актуальную версию перед повторной отправкой.",
        fieldErrors: {},
        canRefresh: true
      };
    }
    if (issue.code === "company_exists") {
      return {
        message: "У этого аккаунта уже есть компания. Загрузите актуальные сведения из кабинета.",
        fieldErrors: {},
        canRefresh: true
      };
    }
    if (issue.code === "company_blocked" || issue.status === 403) {
      return { message: "Компания заблокирована и не может быть изменена.", fieldErrors: {} };
    }
    if (issue.status === 401) {
      return { message: "Сессия закончилась. Войдите в кабинет снова и повторите попытку.", fieldErrors: {} };
    }
    if (Object.keys(issue.fieldErrors).length) {
      return {
        message: "Проверьте поля, отмеченные сообщениями об ошибке.",
        fieldErrors: issue.fieldErrors
      };
    }
    if (issue.status >= 500) {
      return { message: "Сервис временно недоступен. Повторите попытку через несколько минут.", fieldErrors: {}, canRefresh: true };
    }
    return { message: issue.message || "Не удалось сохранить сведения о компании.", fieldErrors: {} };
  }
  return { message: issue instanceof Error ? issue.message : "Не удалось сохранить сведения о компании.", fieldErrors: {} };
}

export function CompanyForm({ initialCompany, companyRole }: { initialCompany: Company | null; companyRole?: CompanyRole | null }) {
  const [company, setCompany] = useState(initialCompany);
  const [businessHours, setBusinessHours] = useState<CompanyHours>(() => initialCompany?.business_hours || emptyBusinessHours());
  const [scheduleEnabled, setScheduleEnabled] = useState(Boolean(initialCompany?.business_hours));
  const [createdInThisForm, setCreatedInThisForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [success, setSuccess] = useState("");

  const canManageCompany = !company || createdInThisForm || companyRole === "owner" || companyRole === "admin";
  const canEdit = canManageCompany && company?.status !== "blocked";

  function syncBusinessHours(hours: Company["business_hours"]) {
    setScheduleEnabled(hours !== null);
    setBusinessHours(hours || emptyBusinessHours());
  }

  function updateDayMode(day: CompanyHourDay, mode: "closed" | "open") {
    setBusinessHours((current) => {
      const existing = current[day];
      const nextDay = mode === "closed"
        ? { closed: true as const }
        : { open: "open" in existing ? existing.open : "", close: "open" in existing ? existing.close : "" };
      return { ...current, [day]: nextDay };
    });
  }

  function updateDayTime(day: CompanyHourDay, field: "open" | "close", value: string) {
    setBusinessHours((current) => {
      const existing = current[day];
      const open = "open" in existing ? existing.open : "";
      const close = "open" in existing ? existing.close : "";
      return { ...current, [day]: { open: field === "open" ? value : open, close: field === "close" ? value : close } };
    });
  }

  async function reloadCompany() {
    setRefreshing(true);
    setError(null);
    setSuccess("");
    try {
      const result = await api.company();
      setCompany(result.company);
      syncBusinessHours(result.company?.business_hours ?? null);
      setSuccess(result.company ? "Актуальные сведения загружены." : "Сведения о компании ещё не созданы.");
    } catch (issue) {
      setError({ ...describeError(issue), message: "Не удалось загрузить актуальные сведения. Повторите попытку." });
    } finally {
      setRefreshing(false);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess("");
    setBusy(true);
    const data = new FormData(event.currentTarget);
    const fields: CompanyFields = {
      name: String(data.get("name") || "").trim(),
      unp: String(data.get("unp") || "").trim(),
      address: String(data.get("address") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      business_hours: scheduleEnabled ? businessHours : null
    };
    const previousStatus = company?.status;
    try {
      const result = company
        ? await api.updateCompany(company.id, company.revision, fields)
        : await api.createCompany(fields);
      setCompany(result.company);
      if (!company) setCreatedInThisForm(true);
      syncBusinessHours(result.company.business_hours);
      if (!previousStatus) setSuccess("Заявка компании отправлена на проверку.");
      else if (result.company.status === "pending" && previousStatus !== "pending") setSuccess("Изменения сохранены и отправлены на повторную проверку.");
      else setSuccess("Изменения сохранены.");
    } catch (issue) {
      setError(describeError(issue));
    } finally {
      setBusy(false);
    }
  }

  const status = company ? statusCopy[company.status] : null;
  const fieldError = (field: string) => error?.fieldErrors[field];
  const formKey = company ? `${company.id}-${company.revision}` : "new-company";

  return (
    <section className="form-section company-form" aria-labelledby="company-form-title">
      <header className="company-form-heading">
        <div>
          <p className="eyebrow">Профиль продавца</p>
          <h2 id="company-form-title">Сведения о компании</h2>
          <p className="muted">Укажите юридические данные и контакт, который увидит модератор.</p>
        </div>
        {company && <span className={`status-pill status-${company.status}`}>{status?.label}</span>}
      </header>

      <div className={`company-status-panel${company ? ` company-status-${company.status}` : " company-status-new"}`} role="status" aria-live="polite">
        {company ? (company.status === "approved" ? <ShieldCheck size={19} aria-hidden="true" /> : <Clock3 size={19} aria-hidden="true" />) : <TriangleAlert size={19} aria-hidden="true" />}
        <div>
          <strong>{company ? status?.label : "Заявка ещё не создана"}</strong>
          <p>{company ? status?.message : "Заполните форму и отправьте заявку. После сохранения её проверит модератор."}</p>
          {company?.status === "rejected" && company.moderation_reason?.trim() && <p className="company-moderation-reason" role="alert"><strong>Причина:</strong> {company.moderation_reason}</p>}
          {company?.status === "blocked" && company.moderation_reason?.trim() && <p className="company-moderation-reason" role="alert"><strong>Комментарий модератора:</strong> {company.moderation_reason}</p>}
          {company?.status === "approved" && <div className="company-links"><Link className="text-link" href={`/dealers/${encodeURIComponent(company.slug)}`}>Открыть страницу компании <ArrowRight size={15} aria-hidden="true" /></Link><Link className="text-link" href="/account/listings">Открыть объявления <ArrowRight size={15} aria-hidden="true" /></Link></div>}
        </div>
      </div>

      {company && !canManageCompany && <p className="notice" role="status">Ваша роль — {companyRole ? companyRoleLabels[companyRole] : "участник команды"}. Редактирование доступно владельцу или администратору компании.</p>}

      {error && <div className="notice company-error" role="alert">
        <p>{error.message}</p>
        {Object.entries(error.fieldErrors).length > 0 && <ul className="company-field-errors">{Object.entries(error.fieldErrors).map(([field, message]) => <li key={field}>{fieldMessage(field, message)}</li>)}</ul>}
        {error.canRefresh && <button className="button button-secondary button-small" type="button" onClick={reloadCompany} disabled={refreshing}><RefreshCw size={15} aria-hidden="true" /> {refreshing ? "Загружаем…" : "Загрузить актуальные сведения"}</button>}
      </div>}

      <form key={formKey} className="form-grid" onSubmit={submit}>
        <label className="field" htmlFor="company-name"><span>Название компании</span><input id="company-name" name="name" required maxLength={180} defaultValue={company?.name || ""} disabled={!canEdit} aria-invalid={Boolean(fieldError("name"))} aria-describedby={fieldError("name") ? "company-name-error" : undefined} />{fieldError("name") && <small id="company-name-error" className="inline-error">{fieldError("name")}</small>}</label>
        <label className="field" htmlFor="company-unp"><span>УНП</span><input id="company-unp" name="unp" required inputMode="numeric" pattern="[0-9]{9}" minLength={9} maxLength={9} defaultValue={company?.unp || ""} disabled={!canEdit} aria-invalid={Boolean(fieldError("unp"))} aria-describedby={fieldError("unp") ? "company-unp-error" : "company-unp-hint"} /><small id="company-unp-hint" className="muted">9 цифр; подлинность подтверждает модератор.</small>{fieldError("unp") && <small id="company-unp-error" className="inline-error">{fieldError("unp")}</small>}</label>
        <label className="field wide" htmlFor="company-address"><span>Юридический адрес</span><input id="company-address" name="address" required maxLength={300} defaultValue={company?.address || ""} disabled={!canEdit} aria-invalid={Boolean(fieldError("address"))} aria-describedby={fieldError("address") ? "company-address-error" : undefined} />{fieldError("address") && <small id="company-address-error" className="inline-error">{fieldError("address")}</small>}</label>
        <label className="field" htmlFor="company-phone"><span>Телефон компании</span><input id="company-phone" name="phone" type="tel" required maxLength={40} defaultValue={company?.phone || ""} disabled={!canEdit} aria-invalid={Boolean(fieldError("phone"))} aria-describedby={fieldError("phone") ? "company-phone-error" : undefined} />{fieldError("phone") && <small id="company-phone-error" className="inline-error">{fieldError("phone")}</small>}</label>
        <section className="wide" aria-labelledby="company-business-hours-title">
          <div className="section-heading"><h3 id="company-business-hours-title">Режим работы</h3></div>
          <label className="check-field"><input type="checkbox" name="business_hours_enabled" checked={scheduleEnabled} disabled={!canEdit} onChange={(event) => setScheduleEnabled(event.currentTarget.checked)} /><span>Указать расписание на публичной странице компании</span></label>
          <p className="muted">Если расписание не указано, на странице компании будет показано «Режим работы не указан».</p>
          {scheduleEnabled ? <div className="company-hours-editor">
            <table className="info-table company-hours-table" role="table">
              <thead><tr><th scope="col">День недели</th><th scope="col">Режим</th><th scope="col">Часы</th></tr></thead>
              <tbody>{companyDays.map(({ key, label }) => {
                const hours = businessHours[key];
                const closed = "closed" in hours;
                const openingError = fieldError(`business_hours.${key}.open`);
                const closingError = fieldError(`business_hours.${key}.close`);
                return <tr key={key}>
                  <th scope="row">{label}</th>
                  <td><select className="form-control" name={`business_hours.${key}.mode`} aria-label={`${label}: режим`} value={closed ? "closed" : "open"} disabled={!canEdit} onChange={(event) => updateDayMode(key, event.currentTarget.value as "closed" | "open")}><option value="closed">Выходной</option><option value="open">Открыто</option></select></td>
                  <td>{closed ? <span className="muted">—</span> : <div className="form-grid">
                    <label className="field"><span>Открытие</span><input type="time" name={`business_hours.${key}.open`} required value={hours.open} disabled={!canEdit} aria-invalid={Boolean(openingError)} aria-describedby={openingError ? `company-hours-${key}-open-error` : undefined} onChange={(event) => updateDayTime(key, "open", event.currentTarget.value)} />{openingError && <small id={`company-hours-${key}-open-error`} className="inline-error">{openingError}</small>}</label>
                    <label className="field"><span>Закрытие</span><input type="time" name={`business_hours.${key}.close`} required value={hours.close} disabled={!canEdit} aria-invalid={Boolean(closingError)} aria-describedby={closingError ? `company-hours-${key}-close-error` : undefined} onChange={(event) => updateDayTime(key, "close", event.currentTarget.value)} />{closingError && <small id={`company-hours-${key}-close-error`} className="inline-error">{closingError}</small>}</label>
                  </div>}</td>
                </tr>;
              })}</tbody>
            </table>
          </div> : <p className="muted" role="status">Режим работы не указан.</p>}
        </section>
        <div className="wide form-actions"><span aria-live="polite" className={success ? "inline-success" : "muted"}>{success}</span><button className="button button-primary" type="submit" disabled={busy || refreshing || !canEdit}>{busy ? "Сохраняем…" : <><Save size={16} aria-hidden="true" /> {company ? "Сохранить изменения" : "Отправить на проверку"}</>}</button></div>
      </form>
    </section>
  );
}
