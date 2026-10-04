"use client";

import { useState, type FormEvent } from "react";
import { History, RefreshCw, Save } from "lucide-react";
import { ARTICLE_TOPIC_LABELS } from "@/lib/content";
import { contentApi, type ContentItem, type ContentKind, type ContentVersion } from "@/lib/content";

const labels: Record<ContentKind, string> = { notification_template: "Шаблоны уведомлений", seo_page: "SEO-страницы", legal_document: "Юридические документы", article: "Полезная информация" };
const predefined: Partial<Record<ContentKind, [string, string][]>> = {
  notification_template: [["saved_search_email", "Сохранённый поиск"], ["email_verification", "Подтверждение почты"], ["password_recovery", "Восстановление доступа"]],
  legal_document: [["terms_of_use", "Условия использования"], ["privacy_policy", "Политика конфиденциальности"], ["cookie_policy", "Политика cookie"], ["listing_rules", "Правила объявлений"], ["commercial_offer", "Оферта"], ["complaints_policy", "Обращения и блокировки"]]
};

function text(data: Record<string, unknown>, key: string) { return typeof data[key] === "string" ? data[key] as string : ""; }
function sourceText(value: unknown) {
  if (!Array.isArray(value)) return "";
  return value.flatMap(item => typeof item === "object" && item !== null && "title" in item && "url" in item
    && typeof item.title === "string" && typeof item.url === "string" ? [`${item.title} | ${item.url}`] : []).join("\n");
}

export function ManagedContentEditor({ initialItems, initialError }: { initialItems: ContentItem[]; initialError: boolean }) {
  const [items, setItems] = useState(initialItems);
  const [newArticleSequence, setNewArticleSequence] = useState(0);
  const [kind, setKind] = useState<ContentKind>("notification_template");
  const [key, setKey] = useState("saved_search_email");
  const [versionList, setVersionList] = useState<ContentVersion[] | null>(null);
  const [error, setError] = useState<string | null>(initialError ? "Не удалось загрузить материалы. Обновите список." : null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const current = items.find(item => item.kind === kind && item.key === key);
  const payload = (current?.payload || {}) as Record<string, unknown>;
  const operator = typeof payload.operator === "object" && payload.operator !== null ? payload.operator as Record<string, unknown> : {};

  async function refresh() {
    setPending(true);
    try { setItems(await contentApi.listAll()); setError(null); }
    catch { setError("Не удалось загрузить материалы. Повторите попытку."); }
    finally { setPending(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const get = (name: string) => String(values.get(name) || "");
    if (!get("current_password")) { setError("Введите пароль администратора."); return; }
    if (!get("reason").trim()) { setError("Укажите причину изменения."); return; }
    if (values.get("confirmation") !== "on") { setError("Подтвердите сохранение материала."); return; }
    const status = get("status") as "draft" | "published";
    const data: Record<string, unknown> = kind === "notification_template" ? { subject: get("subject"), body: get("body") } : {
      title: get("title"), body: get("body")
    };
    if (kind === "seo_page") Object.assign(data, { description: get("description"), heading: get("heading"), canonical_path: get("canonical_path"), minimum_results: Number(get("minimum_results")), indexable: values.get("indexable") === "on",
      filters: Object.fromEntries(["make_id", "model_id", "region_id", "city_id"].map(name => [name, get(name).trim()]).filter(([, value]) => value)) });
    if (kind === "legal_document") Object.assign(data, { document_version: get("document_version"), approved: values.get("approved") === "on", operator: {
      legal_name: get("legal_name"), unp: get("unp"), address: get("address"), contact_email: get("contact_email")
    } });
    if (kind === "article") {
      const publishedAt = get("published_at");
      const sources = get("sources").split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
        const separator = line.indexOf("|");
        return separator < 0 ? null : { title: line.slice(0, separator).trim(), url: line.slice(separator + 1).trim() };
      });
      if (sources.some(source => !source?.title || !source.url)) { setError("Укажите источник в формате «название | https://адрес»."); return; }
      if (status === "published" && !publishedAt) { setError("Для публикации укажите дату публикации."); return; }
      Object.assign(data, { slug: key.trim(), summary: get("summary"), topic: get("topic"),
        published_at: publishedAt || null, sources });
    }
    setPending(true); setError(null); setSuccess(null);
    try {
      const result = await contentApi.save(kind, key, { payload: data, status: get("status") as "draft" | "published", expected_revision: current?.revision || 0,
        reason: get("reason"), current_password: get("current_password"), confirmation: "UPDATE_CONTENT" });
      setItems(previous => [...previous.filter(item => !(item.kind === kind && item.key === key)), result.content]);
      setVersionList(null); setSuccess(`Сохранена редакция ${result.content.revision}.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось сохранить материал."); }
    finally {
      const password = form.elements.namedItem("current_password") as HTMLInputElement | null;
      if (password) password.value = "";
      setPending(false);
    }
  }

  return <section className="info-content">
    <div className="admin-filter-form">
      <label className="field"><span>Раздел</span><select value={kind} onChange={event => { const next = event.target.value as ContentKind; setKind(next); setKey(predefined[next]?.[0][0] || ""); setVersionList(null); setError(null); }}>
        {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {kind === "article" && <>
        <label className="field"><span>Существующая статья</span><select name="existing_article" value={current?.key || ""} disabled={pending} onChange={event => { setKey(event.target.value); setVersionList(null); setError(null); setSuccess(null); }}>
          <option value="">Выберите статью</option>
          {items.filter(item => item.kind === "article").map(item => <option key={item.key} value={item.key}>{text(item.payload as Record<string, unknown>, "title") || item.key} · {item.key}</option>)}
        </select></label>
        <button type="button" className="button button-secondary" disabled={pending} onClick={() => { setKey(""); setNewArticleSequence(value => value + 1); setVersionList(null); setError(null); setSuccess(null); }}>Новая статья</button>
      </>}
      <label className="field"><span>{kind === "article" ? "Slug статьи" : "Материал"}</span>{predefined[kind] ? <select value={key} onChange={event => { setKey(event.target.value); setVersionList(null); }}>{predefined[kind]!.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select> : <><input name="content_key" value={key} maxLength={100} pattern={kind === "article" ? "[a-z0-9]+(-[a-z0-9]+)*" : "[a-z0-9_-]+"} required={kind === "article"} disabled={kind === "article" && Boolean(current)} onChange={event => setKey(event.target.value)} /></>}</label>
      <button type="button" className="button button-secondary" disabled={pending} onClick={refresh}><RefreshCw size={16} />Обновить</button>
    </div>
    {kind === "article" && <p className="muted">Выберите существующую статью или начните новую. Кнопка «Обновить» загружает все страницы списка материалов.</p>}
    <p className="muted">{current ? `Редакция ${current.revision} · ${current.status === "published" ? "Опубликован" : "Черновик"}` : "Новый материал"}</p>
    {error && <p className="notice" role="alert">{error}</p>}{success && <p className="notice" role="status">{success}</p>}
    <form key={`${kind}:${key}:${current?.revision || 0}:${newArticleSequence}`} className="company-form" onSubmit={submit}>
      {kind === "notification_template" ? <label className="field"><span>Тема письма</span><input name="subject" required maxLength={180} defaultValue={text(payload, "subject")} /></label> : <label className="field"><span>Заголовок</span><input name="title" required maxLength={180} defaultValue={text(payload, "title")} /></label>}
      {kind === "seo_page" && <>
        <label className="field"><span>Описание для поиска</span><textarea name="description" required minLength={10} maxLength={500} defaultValue={text(payload, "description")} /></label>
        <label className="field"><span>Заголовок страницы</span><input name="heading" required maxLength={180} defaultValue={text(payload, "heading")} /></label>
        <label className="field"><span>Канонический путь</span><input name="canonical_path" required defaultValue={text(payload, "canonical_path")} /></label>
        <label className="field"><span>Минимум объявлений</span><input name="minimum_results" type="number" min={5} max={100} defaultValue={typeof payload.minimum_results === "number" ? payload.minimum_results : 5} /></label>
        <label><input name="indexable" type="checkbox" defaultChecked={payload.indexable === true} /> Разрешить индексацию при достаточной выдаче</label>
        {(["make_id", "model_id", "region_id", "city_id"] as const).map((name, index) => <label className="field" key={name}><span>{["ID марки", "ID модели", "ID области", "ID города"][index]}</span><input name={name} defaultValue={text((payload.filters || {}) as Record<string, unknown>, name)} /></label>)}
      </>}
      {kind === "legal_document" && <>
        <label className="field"><span>Версия документа</span><input name="document_version" required maxLength={80} defaultValue={text(payload, "document_version")} /></label>
        <label className="field"><span>Название оператора</span><input name="legal_name" required maxLength={180} defaultValue={text(operator, "legal_name")} /></label>
        <label className="field"><span>УНП</span><input name="unp" required pattern="[0-9]{9}" inputMode="numeric" defaultValue={text(operator, "unp")} /></label>
        <label className="field"><span>Адрес оператора</span><input name="address" required maxLength={300} defaultValue={text(operator, "address")} /></label>
        <label className="field"><span>Почта для обращений</span><input name="contact_email" type="email" required defaultValue={text(operator, "contact_email")} /></label>
        <label><input name="approved" type="checkbox" defaultChecked={payload.approved === true} /> Документ утверждён владельцем и юридически проверен</label>
      </>}
      {kind === "article" && <>
        <label className="field wide"><span>Краткое описание</span><textarea name="summary" rows={3} required minLength={20} maxLength={600} defaultValue={text(payload, "summary")} /></label>
        <label className="field"><span>Тематический раздел</span><select name="topic" required defaultValue={text(payload, "topic") || "vehicle_selection"}>{Object.entries(ARTICLE_TOPIC_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field"><span>Дата публикации</span><input name="published_at" type="date" defaultValue={text(payload, "published_at")} /></label>
        <label className="field wide"><span>Проверенные источники</span><textarea name="sources" rows={4} placeholder="Название источника | https://адрес (по одному на строку)" defaultValue={sourceText(payload.sources)} /></label>
      </>}
      <label className="field wide"><span>Текст</span><textarea name="body" rows={12} required minLength={kind === "article" ? 40 : undefined} maxLength={kind === "legal_document" ? 100000 : kind === "article" ? 50000 : 20000} defaultValue={text(payload, "body")} /></label>
      <label className="field"><span>Статус</span><select name="status" defaultValue={current?.status || "draft"}><option value="draft">Черновик</option><option value="published">Опубликован</option></select></label>
      <label className="field wide"><span>Причина изменения</span><textarea name="reason" required maxLength={1000} /></label>
      <label className="field"><span>Пароль администратора</span><input name="current_password" type="password" required autoComplete="current-password" /></label>
      <label><input name="confirmation" type="checkbox" /> Подтверждаю сохранение этой редакции</label>
      <button className="button" type="submit" disabled={pending || !key}><Save size={16} />{pending ? "Сохранение" : "Сохранить"}</button>
    </form>
    {current && <button type="button" className="button button-secondary" onClick={async () => { try { setVersionList((await contentApi.versions(kind, key)).items); } catch { setError("Не удалось загрузить историю."); } }}><History size={16} />История редакций</button>}
    {versionList && <ol className="account-list">{versionList.map(version => <li key={version.revision} className="account-list-item"><div><strong>Редакция {version.revision}</strong><p>{version.reason}</p><time dateTime={version.created_at}>{new Date(version.created_at).toLocaleString("ru-RU")}</time><details><summary>Текст редакции</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{text(version.payload as Record<string, unknown>, "body")}</pre></details></div></li>)}</ol>}
  </section>;
}
