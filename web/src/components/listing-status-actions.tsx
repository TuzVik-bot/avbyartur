"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Pause, Play, ShoppingBag } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Listing } from "@/lib/types";

export function ListingStatusActions({ listing }: { listing: Listing }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function change(action: "pause" | "resume" | "sold") {
    setBusy(true);
    setError("");
    try {
      await api.listingAction(listing.id, action, listing.revision);
      router.refresh();
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось изменить объявление");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="account-item-actions">
      {["draft", "rejected", "pending_review", "active", "paused"].includes(listing.status) && <Link className="button button-secondary button-small" href={`/sell?listing=${encodeURIComponent(listing.id)}`}>Открыть</Link>}
      {listing.status === "active" && <>
        <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => change("pause")}><Pause size={14} /> Снять</button>
        <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => change("sold")}><ShoppingBag size={14} /> Продано</button>
      </>}
      {listing.status === "paused" && <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => change("resume")}><Play size={14} /> Возобновить</button>}
      {error && <span className="inline-error" role="alert">{error}</span>}
      {!error && !busy && listing.status === "sold" && <span className="inline-success"><Check size={14} /> Завершено</span>}
    </div>
  );
}
