"use client";

import Image from "next/image";
import Link from "next/link";
import { Eye, Heart } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompareButton } from "@/components/compare-button";
import { FavoritePriceDropToggle } from "@/components/favorite-price-drop-toggle";
import { ListingPhotoBadges } from "@/components/listing-photo-badges";
import { api, ApiClientError } from "@/lib/api";
import { formatMileage, formatMoney, listingHref, listingPhotoAlt, vehicleLabel } from "@/lib/format";
import type { ListingSummary, Money } from "@/lib/types";
import { userMessage } from "@/lib/user-message";
import styles from "./listing-card.module.css";

const fallbackPhoto = "/vehicles/silver-wagon.png";

type MarketComparison = {
  label: "below_market" | "above_market";
  median_byn: string;
  sample_size: number;
  seller_count: number;
  as_of: string;
  rate_date: string | null;
  difference_percent?: number | null;
};

type LastPriceDrop = {
  amount: string;
  previous_amount: string;
  currency: Money["currency"];
  changed_at: string;
};

type CardListing = Omit<ListingSummary, "promotion_badges"> & {
  promotion_badges?: ("bump" | "highlight" | "top" | "urgent")[];
  published_at?: string | null;
  engine_volume_l?: string | number | null;
  power_hp?: number | null;
  price: (Money & { market_comparison?: MarketComparison | null }) | null;
  last_price_drop?: LastPriceDrop | null;
};

function priceDropText(drop: LastPriceDrop | null | undefined) {
  if (!drop) return null;
  const difference = Number(drop.previous_amount) - Number(drop.amount);
  if (!Number.isFinite(difference) || difference <= 0) return null;
  return `Цена снижена на ${formatMoney({ amount: String(difference), currency: drop.currency })}`;
}

function minskDateParts(value: Date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Minsk", year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(value);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function publishedAge(value?: string | null) {
  if (!value) return null;
  const published = new Date(value);
  if (!Number.isFinite(published.getTime())) return null;
  const publishedParts = minskDateParts(published);
  const todayParts = minskDateParts(new Date());
  const publishedDay = Date.UTC(Number(publishedParts.year), Number(publishedParts.month) - 1, Number(publishedParts.day));
  const todayDay = Date.UTC(Number(todayParts.year), Number(todayParts.month) - 1, Number(todayParts.day));
  if (publishedDay > todayDay) return null;
  const days = Math.floor((todayDay - publishedDay) / 86_400_000);
  if (days === 0) return "Опубликовано сегодня";
  if (days === 1) return "Опубликовано вчера";
  return `Опубликовано ${russianCount(days, "день", "дня", "дней")} назад`;
}

function russianCount(value: number, one: string, few: string, many: string) {
  const plural = new Intl.PluralRules("ru").select(value);
  const noun = plural === "one" ? one : plural === "few" ? few : many;
  return `${value} ${noun}`;
}

function marketTooltip(comparison: MarketComparison) {
  const asOf = new Date(/^\d{4}-\d{2}-\d{2}$/.test(comparison.as_of) ? `${comparison.as_of}T12:00:00+03:00` : comparison.as_of);
  const date = Number.isFinite(asOf.getTime())
    ? new Intl.DateTimeFormat("ru-BY", { timeZone: "Europe/Minsk", day: "2-digit", month: "2-digit", year: "numeric" }).format(asOf)
    : comparison.as_of;
  const sample = russianCount(comparison.sample_size, "объявлению", "объявлениям", "объявлениям");
  const sellers = russianCount(comparison.seller_count, "продавца", "продавцов", "продавцов");
  const median = formatMoney({ amount: comparison.median_byn, currency: "BYN" });
  return `По предложениям Авторынка: медианная цена по ${sample} (от ${sellers}): ${median}. Дата расчёта: ${date}.`;
}

function listingImageSizes(variant: "grid" | "row") {
  if (variant === "row") return "(max-width: 520px) calc(100vw - 24px), 220px";
  return "(max-width: 520px) calc(100vw - 24px), (max-width: 800px) calc((100vw - 42px) / 2), (max-width: 1020px) calc((100vw - 54px) / 2), min(431px, calc((100vw - 68px) / 3))";
}

export function ListingCard({ listing, variant = "grid", saved = false }: { listing: CardListing; variant?: "grid" | "row"; saved?: boolean }) {
  const href = listingHref(listing);
  const photo = listing.photo_urls?.find(Boolean) || listing.cover_url || fallbackPhoto;
  const hasActualPhoto = Boolean(listing.photo_urls?.some(Boolean) || listing.cover_url);
  const title = listing.title || [listing.make?.name, listing.model?.name, listing.year].filter(Boolean).join(" ") || "Автомобиль без названия";
  const comparison = listing.price?.market_comparison;
  const age = publishedAge(listing.published_at);
  const priceDrop = priceDropText(listing.last_price_drop);
  const engineVolumeValue = listing.engine_volume_l;
  const engineVolume = typeof engineVolumeValue === "string"
    ? engineVolumeValue.trim() ? Number(engineVolumeValue) : null
    : engineVolumeValue ?? null;
  return (
    <article className={`listing-card ${styles.card} ${variant === "row" ? "listing-row" : ""}`}>
      <div className="listing-card-media">
        <Link href={href} aria-label={`Открыть объявление ${title}`}>
          <Image src={photo} alt={hasActualPhoto ? listingPhotoAlt(title) : `Синтетическое изображение для объявления «${title}»`} width={900} height={563} sizes={listingImageSizes(variant)} priority={false} />
        </Link>
        {!hasActualPhoto && <span className="synthetic-label">Синтетическое фото</span>}
        {hasActualPhoto && <ListingPhotoBadges badges={listing.photo_badges} />}
        {listing.promotion_badges?.includes("urgent") && <span className={styles.urgentBadge} data-urgent-badge>Срочно</span>}
        <FavoriteButton listingId={listing.id} listingTitle={title} href={href} initialSaved={saved} />
        <CompareButton listingId={listing.id} />
      </div>
      <div className="card-body">
        <Link className="card-title" href={href}>{title}</Link>
        {listing.in_transit && <span className="status-pill">Авто в пути · указано продавцом</span>}
        <div className="card-price-line">
          <p className="card-price">{formatMoney(listing.price)}</p>
          {comparison && <span className={`market-badge ${comparison.label}`} data-market-comparison title={marketTooltip(comparison)} tabIndex={0} aria-label={`${comparison.label === "below_market" ? "Цена ниже рынка" : "Цена выше рынка"}. ${marketTooltip(comparison)}`}>{comparison.label === "below_market" ? "Цена ниже рынка" : "Цена выше рынка"}</span>}
          {priceDrop && <span className={styles.priceDropBadge} data-price-drop>{priceDrop}</span>}
        </div>
        <div className="card-specs">
          <span>{listing.year ? `${listing.year} г.` : "Год не указан"}</span>
          <span>{formatMileage(listing.mileage_km)}</span>
          {listing.fuel !== "electric" && engineVolume !== null && Number.isFinite(engineVolume) && <span>{new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 1 }).format(engineVolume)} л</span>}
          {typeof listing.power_hp === "number" && Number.isFinite(listing.power_hp) && <span>{listing.power_hp} л.с.</span>}
          <span>{vehicleLabel(listing.fuel)}</span>
          <span>{vehicleLabel(listing.transmission)}</span>
        </div>
        {age && <p className="card-published" suppressHydrationWarning>{age}</p>}
        <div className="card-footer">
          <span className={`seller-tag ${listing.seller.type === "private" ? "private" : ""}`}>
            <span aria-hidden="true">{!listing.is_imported && listing.seller.type === "company" ? "◆" : "●"}</span>
            {listing.is_imported ? (listing.provenance?.source_name || "Источник объявления") : listing.seller.type === "company" ? "Компания" : "Частный продавец"}
          </span>
          {listing.city?.slug ? <Link href={`/cars/city/${encodeURIComponent(listing.city.slug)}`}>{listing.city.name}</Link> : <span>{listing.manual_city || "Населённый пункт не указан"}</span>}
        </div>
        <div className="card-actions">{listing.view_count != null && <span className="listing-views" role="img" aria-label={`Просмотры: ${listing.view_count}`}><Eye size={15} aria-hidden="true" /> {listing.view_count.toLocaleString("ru-BY")}</span>}</div>
      </div>
    </article>
  );
}

export function FavoriteButton({ listingId, listingTitle, href, initialSaved, placement = "overlay" }: {
  listingId: string;
  listingTitle?: string;
  href: string;
  initialSaved: boolean;
  placement?: "overlay" | "inline";
}) {
  const { user } = useAuth();
  const router = useRouter();
  const [saved, setSaved] = useState(initialSaved);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  // The price-drop alert is offered only right after this user saved the listing here.
  const [offerPriceAlert, setOfferPriceAlert] = useState(false);

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
      setOfferPriceAlert(!saved);
      if (saved) router.refresh();
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        router.push(`/login?next=${encodeURIComponent(href)}`);
      } else {
        setMessage(userMessage(error, "Не удалось изменить избранное"));
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
      {offerPriceAlert && user && <div className={placement === "inline" ? styles.priceAlertInline : styles.priceAlertOverlay}>
        <FavoritePriceDropToggle
          listingId={listingId}
          listingTitle={listingTitle || "объявление"}
          initialEnabled={false}
          label="Сообщить о снижении цены"
          loginNext={href}
        />
      </div>}
    </>
  );
}
