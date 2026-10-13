"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { photoBadgeOptions } from "@/lib/photo-badges";
import type { Listing, PhotoBadge } from "@/lib/types";

export function ListingPhotoBadgeEditor({ listing, disabled = false }: { listing: Listing; disabled?: boolean }) {
  const router = useRouter();
  const [badges, setBadges] = useState<PhotoBadge[]>(listing.photo_badges || []);
  const [revision, setRevision] = useState(listing.revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    setBadges(listing.photo_badges || []);
    setRevision(listing.revision);
  }, [listing.id, listing.revision, listing.photo_badges]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.setListingPhotoBadges(listing.id, revision, badges);
      setBadges(result.listing.photo_badges || []);
      setRevision(result.listing.revision);
      setMessage("Метки сохранены");
      router.refresh();
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось сохранить метки");
    } finally { setBusy(false); }
  }

  return <form className="photo-badge-editor" onSubmit={save}>
    <fieldset disabled={busy || disabled}>
      <legend>Метки на фото</legend>
      <p className="muted">Включайте метки после подтверждения проверки, бесплатной истории или лучшей цены. Изменения продавца сбросят метки.</p>
      {photoBadgeOptions.map(({ value, label }) => <label key={value}>
        <input type="checkbox" checked={badges.includes(value)} onChange={(event) => {
          setBadges((current) => event.target.checked ? [...current, value] : current.filter((badge) => badge !== value));
          setMessage("");
        }} />{label}
      </label>)}
      <button className="button button-secondary button-small" type="submit">{busy ? "Сохранение…" : "Сохранить метки"}</button>
    </fieldset>
    {error && <p role="alert" className="inline-error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </form>;
}
