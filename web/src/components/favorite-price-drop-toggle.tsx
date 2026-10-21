"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiClientError, api } from "@/lib/api";
import styles from "./favorite-price-drop-toggle.module.css";

export function FavoritePriceDropToggle({
  listingId,
  listingTitle,
  initialEnabled
}: {
  listingId: string;
  listingTitle: string;
  initialEnabled: boolean;
}) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(initialEnabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function changeEnabled(nextEnabled: boolean) {
    if (busy) return;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await api.setFavoritePriceDropAlert(listingId, nextEnabled);
      setEnabled(result.enabled);
      setNotice(result.enabled
        ? "Уведомления о снижении цены включены."
        : "Уведомления о снижении цены выключены.");
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) {
        router.push(`/login?next=${encodeURIComponent("/account/favorites")}`);
      } else {
        setError("Не удалось сохранить настройку уведомления. Повторите попытку.");
      }
    } finally {
      setBusy(false);
    }
  }

  return <div className={styles.toggle} data-testid="favorite-price-drop-toggle" aria-busy={busy}>
    <label className={styles.label}>
      <input
        type="checkbox"
        checked={enabled}
        aria-label={`Уведомлять о снижении цены: ${listingTitle}`}
        disabled={busy}
        onChange={(event) => void changeEnabled(event.currentTarget.checked)}
      />
      <span>Уведомлять о снижении цены</span>
    </label>
    {busy && <p className={styles.muted} role="status">Сохраняем настройку…</p>}
    {notice && <p className={styles.success} role="status">{notice}</p>}
    {error && <p className={styles.error} role="alert">{error}</p>}
  </div>;
}
