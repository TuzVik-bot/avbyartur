"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiClientError } from "@/lib/api";
import {
  adminTariffsApi,
  type AdminTariff,
  type AdminTariffCreateInput,
  type AdminTariffDeleteInput,
  type AdminTariffUpdateInput,
  type TariffCurrency,
  type TariffServiceCode,
  type TariffStatus
} from "@/lib/admin-tariffs";
import styles from "./admin-tariff-editor.module.css";

type EditorMode = { kind: "create" } | { kind: "update" | "delete"; tariff: AdminTariff };

const serviceLabels: Record<TariffServiceCode, string> = {
  bump: "Поднять объявление",
  highlight: "Выделить объявление",
  top: "Разместить вверху",
  dealer_package: "Пакет объявлений дилера"
};

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError) {
    if (issue.code === "revision_conflict") return "Тариф уже изменён. Обновите список и проверьте актуальную ревизию.";
    if (issue.code === "reauthentication_failed") return "Текущий пароль администратора не подошёл.";
    if (issue.code === "tariff_referenced") return "Тариф связан с историей заказов, поэтому удалить его нельзя. Отключите тариф.";
    if (issue.code === "tariff_code_conflict") return "Этот код уже занят. Укажите другой постоянный код тарифа.";
    if (issue.code === "invalid_tariff") return "Проверьте услугу и лимит объявлений в тарифе.";
    if (issue.status === 403) return "Администраторская роль или проверка CSRF больше не активна. Обновите страницу.";
    if (issue.status === 429) return "Слишком много попыток. Подождите и повторите изменение.";
  }
  return issue instanceof Error ? issue.message : "Не удалось сохранить тариф.";
}

function exactAmount(raw: string) {
  const value = raw.trim();
  const match = /^(0|[1-9]\d{0,9})(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) throw new Error("Введите сумму с точностью не более чем двумя знаками после запятой.");
  const cents = BigInt(match[1]) * BigInt("100") + BigInt((match[2] || "").padEnd(2, "0"));
  if (cents <= BigInt("0") || cents > BigInt("999999999999")) throw new Error("Сумма должна быть больше нуля и не превышать 9999999999.99.");
  return `${match[1]}.${(match[2] || "").padEnd(2, "0")}`;
}

function formInteger(value: FormDataEntryValue | null, label: string, minimum: number, maximum: number, nullable = false) {
  const raw = String(value ?? "").trim();
  if (!raw && nullable) return null;
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label}: введите целое число от ${minimum} до ${maximum}.`);
  }
  return parsed;
}

function tariffOrder(a: AdminTariff, b: AdminTariff) {
  return a.service_code.localeCompare(b.service_code) || a.code.localeCompare(b.code);
}

function statusLabel(status: TariffStatus) {
  return status === "active" ? "Активен" : "Отключён";
}

export function AdminTariffEditor({ initialTariffs, initialError }: { initialTariffs: AdminTariff[]; initialError: boolean }) {
  const router = useRouter();
  const [tariffs, setTariffs] = useState(initialTariffs);
  const [mode, setMode] = useState<EditorMode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function openEditor(nextMode: EditorMode) {
    setMode(nextMode);
    setError("");
    setNotice("");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !mode) return;
    const values = new FormData(event.currentTarget);
    const reason = String(values.get("reason") || "").trim();
    const currentPassword = String(values.get("current_password") || "");
    const confirmation = String(values.get("confirmation") || "");
    if (!currentPassword) { setError("Введите текущий пароль администратора для повторной проверки."); return; }
    if (!reason) { setError("Укажите причину изменения."); return; }

    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode.kind === "delete") {
        if (confirmation !== "DELETE_TARIFF") { throw new Error("Введите DELETE_TARIFF для подтверждения удаления."); }
        const payload: AdminTariffDeleteInput = {
          expected_revision: mode.tariff.revision,
          reason,
          confirmation: "DELETE_TARIFF",
          current_password: currentPassword
        };
        await adminTariffsApi.delete(mode.tariff.id, payload);
        setTariffs((current) => current.filter((tariff) => tariff.id !== mode.tariff.id));
        setNotice("Тариф удалён и записан в аудит.");
      } else {
        const amount = exactAmount(String(values.get("amount") || ""));
        const name = String(values.get("name") || "").trim();
        if (!name) throw new Error("Укажите название тарифа.");
        const currency = String(values.get("currency") || "") as TariffCurrency;
        if (currency !== "BYN" && currency !== "USD") throw new Error("Выберите валюту тарифа.");
        const durationDays = formInteger(values.get("duration_days"), "Длительность", 1, 365)!;
        const quota = mode.kind === "create" || mode.tariff.service_code === "dealer_package"
          ? formInteger(values.get("listing_quota"), "Лимит объявлений", 1, 10000, true)
          : null;
        const status = String(values.get("status") || "") as TariffStatus;
        if (status !== "active" && status !== "disabled") throw new Error("Выберите статус тарифа.");
        const tariffService = mode.kind === "create" ? String(values.get("service_code") || "") : mode.tariff.service_code;
        if (tariffService === "dealer_package" && status === "active" && quota === null) throw new Error("Для активного пакета дилера укажите лимит объявлений.");
        if (mode.kind === "create") {
          if (confirmation !== "CREATE_TARIFF") throw new Error("Введите CREATE_TARIFF для подтверждения.");
          const code = String(values.get("code") || "").trim();
          const serviceCode = String(values.get("service_code") || "") as TariffServiceCode;
          if (!/^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$/.test(code)) throw new Error("Код: используйте латинские строчные буквы, цифры, дефис или подчёркивание.");
          if (!Object.hasOwn(serviceLabels, serviceCode)) throw new Error("Выберите тип услуги.");
          const payload: AdminTariffCreateInput = {
            code, service_code: serviceCode, name, amount, currency, duration_days: durationDays,
            listing_quota: quota, status, reason, confirmation: "CREATE_TARIFF", current_password: currentPassword
          };
          const result = await adminTariffsApi.create(payload);
          setTariffs((current) => [...current, result.tariff].sort(tariffOrder));
          setNotice("Тариф создан и записан в аудит. Проверьте его статус перед использованием.");
        } else {
          if (confirmation !== "UPDATE_TARIFF") throw new Error("Введите UPDATE_TARIFF для подтверждения.");
          const payload: AdminTariffUpdateInput = {
            name, amount, currency, duration_days: durationDays, listing_quota: quota, status,
            expected_revision: mode.tariff.revision, reason, confirmation: "UPDATE_TARIFF", current_password: currentPassword
          };
          const result = await adminTariffsApi.update(mode.tariff.id, payload);
          setTariffs((current) => current.map((tariff) => tariff.id === result.tariff.id ? result.tariff : tariff).sort(tariffOrder));
          setNotice(result.changed ? "Тариф сохранён и записан в аудит." : "Тариф не изменился.");
        }
      }
      setMode(null);
      router.refresh();
    } catch (issue) {
      setError(errorText(issue));
    } finally {
      setBusy(false);
    }
  }

  return <section className={styles.manager} aria-label="Управление тарифами">
    <div className={styles.toolbar}>
      <div><h2>Каталог тарифов</h2><p>Код и услуга после создания не меняются. Изменения цены, срока и доступности получают новую ревизию.</p></div>
      <button className="button button-primary button-small" type="button" disabled={initialError || Boolean(mode)} onClick={() => openEditor({ kind: "create" })}>Создать тариф</button>
    </div>

    {initialError && <p className="notice" role="alert">Не удалось загрузить тарифы. Обновите страницу и повторите попытку.</p>}
    {!initialError && tariffs.length === 0 && !mode && <div className={`empty-state ${styles.empty}`}><h3>Тарифов пока нет</h3><p>Список остаётся пустым, пока владелец не утвердит цены и длительности.</p></div>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && !mode && <p className="inline-error" role="alert">{error}</p>}

    {mode?.kind === "create" && <article className={`admin-tariff-card ${styles.card}`}>
      <div className={styles.cardHeading}><div><p className="eyebrow">Новый тариф</p><h3>Задайте параметры вручную</h3></div></div>
      <TariffForm mode={mode} busy={busy} error={error} onSubmit={submit} onCancel={() => { setMode(null); setError(""); }} />
    </article>}

    {!initialError && tariffs.length > 0 && <div className={styles.list}>
      {tariffs.map((tariff) => <article className={`admin-tariff-card ${styles.card}`} key={tariff.id}>
        <div className={styles.cardHeading}>
          <div><p className="eyebrow">{serviceLabels[tariff.service_code]}</p><h3>{tariff.name}</h3><p className={styles.identity}><code>{tariff.code}</code> · ревизия {tariff.revision}</p></div>
          <div className={styles.price}><strong>{tariff.amount}</strong><span>{tariff.currency}</span></div>
        </div>
        <dl className={styles.details}>
          <div><dt>Статус</dt><dd><span className={tariff.status === "active" ? styles.active : styles.disabled}>{statusLabel(tariff.status)}</span></dd></div>
          <div><dt>Срок</dt><dd>{tariff.duration_days} дн.</dd></div>
          {tariff.service_code === "dealer_package" && <div><dt>Объявлений</dt><dd>{tariff.listing_quota ?? "Не задано"}</dd></div>}
        </dl>
        <div className={styles.actions}>
          <button className="button button-secondary button-small" type="button" disabled={Boolean(mode)} onClick={() => openEditor({ kind: "update", tariff })}>Изменить тариф</button>
          <button className="button button-secondary button-small" type="button" disabled={Boolean(mode)} onClick={() => openEditor({ kind: "delete", tariff })}>Удалить неиспользуемый</button>
        </div>
        {mode?.kind !== "create" && mode?.tariff.id === tariff.id && <TariffForm mode={mode} busy={busy} error={error} onSubmit={submit} onCancel={() => { setMode(null); setError(""); }} />}
      </article>)}
    </div>}
  </section>;
}

function TariffForm({ mode, busy, error, onSubmit, onCancel }: {
  mode: EditorMode;
  busy: boolean;
  error: string;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}) {
  const tariff = mode.kind === "create" ? null : mode.tariff;
  const [selectedServiceCode, setSelectedServiceCode] = useState<TariffServiceCode>(tariff?.service_code ?? "bump");
  const isDelete = mode.kind === "delete";
  const isCreate = mode.kind === "create";
  const serviceCode = isCreate ? undefined : tariff!.service_code;
  const quotaField = isCreate ? selectedServiceCode === "dealer_package" : serviceCode === "dealer_package";

  return <form className={`admin-tariff-form ${styles.form}`} onSubmit={onSubmit}>
    {isDelete ? <>
      <p className={styles.deleteMessage}>Удалить можно только тариф без заказов и платёжной истории. Связанные тарифы оставляйте в архивном статусе «Отключён».</p>
      <label className={`field ${styles.wide}`}><span>Причина удаления</span><textarea name="reason" maxLength={1000} required /></label>
      <label className="field"><span>Текущий пароль администратора</span><input name="current_password" type="password" autoComplete="current-password" maxLength={256} required /></label>
      <label className="field"><span>Введите DELETE_TARIFF</span><input name="confirmation" autoComplete="off" required /></label>
    </> : <>
      {isCreate ? <>
        <label className="field"><span>Постоянный код</span><input name="code" maxLength={80} autoComplete="off" placeholder="например, bump-7-days" required /></label>
        <label className="field"><span>Услуга</span><select name="service_code" value={selectedServiceCode} onChange={(event) => setSelectedServiceCode(event.target.value as TariffServiceCode)}>{Object.entries(serviceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </> : <div className={`${styles.identityBlock} ${styles.wide}`}><span>Идентичность</span><strong><code>{tariff!.code}</code> · {serviceLabels[tariff!.service_code]}</strong><small>Код и тип услуги не редактируются.</small></div>}
      <label className={`field ${styles.wide}`}><span>Название</span><input name="name" maxLength={120} defaultValue={tariff?.name ?? ""} required /></label>
      <label className="field"><span>Цена</span><input name="amount" type="number" inputMode="decimal" min="0.01" max="9999999999.99" step="0.01" defaultValue={tariff?.amount ?? ""} placeholder="Введите цену" required /></label>
      <label className="field"><span>Валюта</span><select name="currency" defaultValue={tariff?.currency ?? ""} required><option value="" disabled>Выберите валюту</option><option value="BYN">BYN</option><option value="USD">USD</option></select></label>
      <label className="field"><span>Срок, дней</span><input name="duration_days" type="number" min="1" max="365" step="1" defaultValue={tariff?.duration_days ?? ""} required /></label>
      {quotaField && <label className="field"><span>Объявлений в пакете</span><input name="listing_quota" type="number" min="1" max="10000" step="1" defaultValue={tariff?.listing_quota ?? ""} placeholder="Не задано" /></label>}
      <label className="field"><span>Статус</span><select name="status" defaultValue={tariff?.status ?? "disabled"}><option value="disabled">Отключён</option><option value="active">Активен</option></select></label>
      <label className={`field ${styles.wide}`}><span>Причина изменения</span><textarea name="reason" maxLength={1000} required /></label>
      <label className="field"><span>Текущий пароль администратора</span><input name="current_password" type="password" autoComplete="current-password" maxLength={256} required /></label>
      <label className="field"><span>Введите {isCreate ? "CREATE_TARIFF" : "UPDATE_TARIFF"}</span><input name="confirmation" autoComplete="off" required /></label>
    </>}
    {error && <p className={`inline-error ${styles.wide}`} role="alert">{error}</p>}
    <div className={`form-actions ${styles.formActions}`}>
      <button className={`button ${isDelete ? "button-danger" : "button-primary"} button-small`} type="submit" disabled={busy}>{busy ? "Сохраняем…" : isDelete ? "Удалить тариф" : isCreate ? "Создать тариф" : "Сохранить тариф"}</button>
      <button className="button button-secondary button-small" type="button" disabled={busy} onClick={onCancel}>Отмена</button>
    </div>
  </form>;
}
