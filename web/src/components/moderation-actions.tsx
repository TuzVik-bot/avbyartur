"use client";
import { ListingEditHistory } from "@/components/listing-edit-history";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Ban, Check, CheckCircle2, CircleX, ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api } from "@/lib/api";
import type { Company, Listing, Report } from "@/lib/types";

export function ListingModerationActions({ listing }: { listing: Listing }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const activeListing = listing.status === "active";

  async function run(action: "approve" | "reject" | "block") {
    if (action !== "approve" && !reason.trim()) { setError("Укажите причину решения."); return; }
    setBusy(true); setError("");
    try { await api.moderateListing(listing.id, action, listing.revision, reason.trim() || undefined); router.refresh(); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось сохранить решение"); }
    finally { setBusy(false); }
  }

  return <div className="moderation-actions">
    {!activeListing && <button className="button button-primary button-small" type="button" disabled={busy} onClick={() => run("approve")}><Check size={15} /> Одобрить</button>}
    {!activeListing && <details className="moderation-reason"><summary className="button button-secondary button-small"><CircleX size={15} /> Отклонить</summary><label className="field"><span>Причина</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} required /></label><button className="button button-danger button-small" type="button" disabled={busy} onClick={() => run("reject")}>Отклонить</button></details>}
    <details className="moderation-reason"><summary className="button button-danger button-small"><Ban size={15} /> Заблокировать</summary><label className="field"><span>Причина</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} required /></label><button className="button button-danger button-small" type="button" disabled={busy} onClick={() => run("block")}>Подтвердить блокировку</button></details>
    <ListingEditHistory listingId={listing.id} />
    {error && <span className="inline-error" role="alert">{error}</span>}
  </div>;
}

export function CompanyModerationActions({ company }: { company: Company }) {
  const { user } = useAuth();
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(action: "approve" | "reject" | "block") {
    if (action !== "approve" && !reason.trim()) { setError("Укажите причину решения."); return; }
    setBusy(true); setError("");
    try { await api.moderateCompany(company.id, action, company.revision, reason.trim() || undefined); router.refresh(); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось сохранить решение"); }
    finally { setBusy(false); }
  }
  return <div className="moderation-actions">
    {user?.role === "admin" && <button className="button button-primary button-small" type="button" disabled={busy} onClick={() => run("approve")}><ShieldCheck size={15} /> Допустить</button>}
    <details className="moderation-reason"><summary className="button button-secondary button-small"><CircleX size={15} /> Отклонить</summary><label className="field"><span>Причина</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} /></label><button className="button button-danger button-small" type="button" disabled={busy} onClick={() => run("reject")}>Отклонить</button></details>
    <details className="moderation-reason"><summary className="button button-danger button-small"><Ban size={15} /> Блокировать</summary><label className="field"><span>Причина</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={1000} required /></label><button className="button button-danger button-small" type="button" disabled={busy} onClick={() => run("block")}>Подтвердить блокировку</button></details>
    {error && <span className="inline-error" role="alert">{error}</span>}
  </div>;
}

export function ReportResolution({ report }: { report: Report }) {
  const router = useRouter();
  const [resolution, setResolution] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resolution.trim()) { setError("Укажите решение."); return; }
    setBusy(true); setError("");
    try { await api.resolveReport(report.id, resolution.trim()); router.refresh(); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось закрыть жалобу"); }
    finally { setBusy(false); }
  }
  return <form className="report-resolution" onSubmit={submit}>
    <label className="field"><span>Решение</span><input value={resolution} onChange={(event) => setResolution(event.target.value)} required maxLength={1000} /></label>
    <button className="button button-secondary button-small" disabled={busy} type="submit"><CheckCircle2 size={15} /> Закрыть жалобу</button>
    {error && <span className="inline-error" role="alert">{error}</span>}
  </form>;
}
