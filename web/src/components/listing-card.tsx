"use client";

import { categoryFacts, categoryPath } from "@/lib/listing-categories";
import Image from "next/image";
import Link from "next/link";
import { Heart } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError } from "@/lib/api";
import { formatMileage, formatMoney, listingHref, vehicleLabel } from "@/lib/format";
import type { ListingSummary } from "@/lib/types";

function listingImageSizes(variant: "grid" | "row") {
  if (variant === "row") return "(max-width: 520px) 118px, 220px";
  return "(max-width: 520px) calc(100vw - 24px), (max-width: 800px) calc((100vw - 42px) / 2), (max-width: 1020px) calc((100vw - 54px) / 2), min(431px, calc((100vw - 68px) / 3))";
}

export function ListingCard({ listing, variant = "grid", saved = false }: { listing: ListingSummary; variant?: "grid" | "row"; saved?: boolean }) {
  const href = listingHref(listing);
  const photo = listing.photo_urls?.find(Boolean) || listing.cover_url || null;
  const title = listing.title || [listing.make?.name, listing.model?.name, listing.year].filter(Boolean).join(" ") || "Объявление без названия";
  return (
    <article className={`listing-card ${variant === "row" ? "listing-row" : ""}`}>
      <div className="listing-card-media">
        <Link className="listing-card-photo-link" href={href} aria-label={`Открыть объявление ${title}`}>
          {photo ? <Image src={photo} alt={`Фотография: ${title}`} width={900} height={563} sizes={listingImageSizes(variant)} unoptimized priority={false} /> : <span className="photo-placeholder" role="img" aria-label="Фото не добавлено"><span>Фото не добавлено</span></span>}
        </Link>
        <FavoriteButton listingId={listing.id} href={href} initialSaved={saved} />
      </div>
      <div className="card-body">
        <Link className="card-title" href={href}>{title}</Link>
        <p className="card-price">{formatMoney(listing.price)}</p>
        <div className="card-specs">
          {categoryFacts(listing).map(([label, value]) => <span key={label}>{value}</span>)}
        </div>
        <div className="card-footer">
          <span className={`seller-tag ${listing.seller.type === "private" ? "private" : ""}`}>
            <span aria-hidden="true">{listing.seller.type === "company" ? "◆" : "●"}</span>
            {listing.seller.type === "company" ? "Компания" : "Частный продавец"}
          </span>
          {listing.city?.slug ? <Link href={listing.category_code && listing.category_code !== "cars" ? `${categoryPath(listing.category_code)}?city_id=${encodeURIComponent(listing.city.id)}` : `/cars/city/${encodeURIComponent(listing.city.slug)}`}>{listing.city.name}</Link> : <span>{listing.manual_city || "Населённый пункт не указан"}</span>}
        </div>
      </div>
    </article>
  );
}

export function FavoriteButton({ listingId, href, initialSaved }: { listingId: string; href: string; initialSaved: boolean }) {
  const { user } = useAuth();
  const router = useRouter();
  const [saved, setSaved] = useState(initialSaved);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function toggle() {
    setMessage("");
    if (!user) {
      router.push(`/login?next=${encodeURIComponent(href)}`);
      return;
    }
    setBusy(true);
    try {
      if (saved) await api.removeFavorite(listingId);
      else await api.addFavorite(listingId);
      setSaved(!saved);
      if (saved) router.refresh();
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        router.push(`/login?next=${encodeURIComponent(href)}`);
      } else {
        setMessage(error instanceof Error ? error.message : "Не удалось изменить избранное");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className={`favorite-button ${saved ? "is-saved" : ""}`} type="button" aria-label={saved ? "Убрать из избранного" : "Добавить в избранное"} aria-pressed={saved} disabled={busy} onClick={toggle}>
        <Heart size={20} fill={saved ? "currentColor" : "none"} />
      </button>
      {message && <span className="favorite-error" role="alert">{message}</span>}
    </>
  );
}
