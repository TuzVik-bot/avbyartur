"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";
import { AlertTriangle, Building2, ChevronLeft, ChevronRight, CircleUserRound, Eye, MapPin, MessageCircle, ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { FavoriteButton, ListingCard } from "@/components/listing-card";
import { ListingPriceHistory } from "@/components/listing-price-history";
import { RecentlyViewedListings } from "@/components/recently-viewed-listings";
import { ListingContactActions } from "@/components/listing-contact-actions";
import { useContactClickConsent } from "@/components/contact-click-consent";
import { ListingTrust } from "@/components/listing-trust";
import { ListingPhotoBadges } from "@/components/listing-photo-badges";
import { SellerListings, type PublicSellerListing } from "@/components/seller-listings";
import { ComparisonAction } from "@/components/comparison/comparison-action";
import { ShareButton } from "@/components/share-button";
import { api, ApiClientError } from "@/lib/api";
import type { ListingMessengerChannel } from "@/lib/api";
import { formatDate, formatMileage, formatMoney, listingHref, listingPhotoAlt, vehicleLabel } from "@/lib/format";
import { trackContactClick, type ContactChannel } from "@/lib/analytics";
import { listingCatalogBreadcrumbs } from "@/lib/listing-breadcrumbs";
import type { Listing, ReportCategory } from "@/lib/types";
import type { components } from "@/lib/types.generated";

const fallbackPhoto = "/vehicles/silver-wagon.png";
const reportCategories: { value: ReportCategory; label: string }[] = [
  { value: "incorrect_info", label: "Недостоверная информация" },
  { value: "duplicate", label: "Повторное объявление" },
  { value: "fraud", label: "Подозрение на мошенничество" },
  { value: "prohibited", label: "Запрещённое объявление" },
  { value: "other", label: "Другое" }
];
const equipmentLabels: Record<string, string> = {
  abs: "Антиблокировочная система тормозов (ABS)", esp: "Система курсовой устойчивости (ESP)", airbags: "Подушки безопасности", air_conditioning: "Кондиционер", climate_control: "Климат-контроль", heated_seats: "Подогрев сидений", cruise_control: "Круиз-контроль", parking_sensors: "Парктроники", rear_camera: "Камера заднего вида", leather_seats: "Кожаный салон", carplay: "Apple CarPlay", android_auto: "Android Auto"
};
const optionLabels: Record<string, string> = {
  black: "Чёрный", white: "Белый", gray: "Серый", silver: "Серебристый", red: "Красный", blue: "Синий", green: "Зелёный", yellow: "Жёлтый", brown: "Коричневый", beige: "Бежевый", orange: "Оранжевый", purple: "Фиолетовый", other: "Другой",
  cleared_rb: "Оформлен в РБ (со слов продавца)", eaeu_import: "Ввезён из ЕАЭС (со слов продавца)", uncleared: "Не растаможен (со слов продавца)", unknown: "Не указано",
  good: "Исправен", needs_repair: "Требует ремонта", non_operational: "Не на ходу", minor_damage: "Есть небольшие повреждения", significant_damage: "Есть серьёзные повреждения", repaired: "Был в ремонте",
  ...equipmentLabels
};

function PriceConversions({ price }: { price: Listing["price"] }) {
  const [rates, setRates] = useState<components["schemas"]["CustomsRatesResponse"] | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!price) return;
    const controller = new AbortController();
    setRates(null);
    setUnavailable(false);
    fetch("/api/v1/customs-calculator/rates", { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Rates unavailable");
        return response.json() as Promise<components["schemas"]["CustomsRatesResponse"]>;
      })
      .then(setRates)
      .catch(() => { if (!controller.signal.aborted) setUnavailable(true); });
    return () => controller.abort();
  }, [price?.amount, price?.currency]);

  if (!price) return null;
  if (unavailable) return <p className="detail-conversion-note">Курс валют временно недоступен</p>;
  if (!rates) return null;

  const amount = Number(price.amount);
  const usdRate = Number(rates.rates.find((rate) => rate.currency === "USD")?.byn_per_unit);
  const eurRate = Number(rates.rates.find((rate) => rate.currency === "EUR")?.byn_per_unit);
  if (![amount, usdRate, eurRate].every((value) => Number.isFinite(value) && value > 0)) {
    return <p className="detail-conversion-note">Курс валют временно недоступен</p>;
  }
  const byn = price.currency === "USD" ? amount * usdRate : amount;
  const format = (value: number) => new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 0 }).format(value);

  return <div className="detail-conversions" role="group" aria-label="Цена в других валютах">
    <div className="detail-conversion-values"><span>≈ {format(byn / usdRate)} USD</span><span>≈ {format(byn / eurRate)} EUR</span></div>
    <p className="detail-conversion-note">По курсу НБРБ на {formatDate(rates.rate_date)}</p>
  </div>;
}

export function ListingDetail({ listing, initialSaved = false, relatedListings = [], sellerListings = [] }: { listing: Listing; initialSaved?: boolean; relatedListings?: import("@/lib/types").ListingSummary[]; sellerListings?: PublicSellerListing[] }) {
  const router = useRouter();
  const { user } = useAuth();
  const { consent } = useContactClickConsent();
  const [phone, setPhone] = useState("");
  const [contactsRevealed, setContactsRevealed] = useState(false);
  const [messengers, setMessengers] = useState<ListingMessengerChannel[]>([]);
  const [phoneError, setPhoneError] = useState("");
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [guestContactRevealEnabled, setGuestContactRevealEnabled] = useState(false);
  const [canManageActiveListing, setCanManageActiveListing] = useState(false);
  const actualPhotos = listing.photo_urls.filter(Boolean);
  const photos = actualPhotos.length ? actualPhotos : [listing.cover_url || fallbackPhoto];
  const [selectedPhotoIndex, setSelectedPhotoIndex] = useState(0);
  const [showAllPhotos, setShowAllPhotos] = useState(false);
  const thumbnailsRef = useRef<HTMLDivElement>(null);
  const safeSelectedPhotoIndex = Math.min(selectedPhotoIndex, photos.length - 1);
  const selectedPhoto = photos[safeSelectedPhotoIndex];
  const hasSyntheticPhoto = !actualPhotos.length && !listing.cover_url;
  const href = listingHref(listing);
  const conversationStartPath = `/account/messages/new?listing_id=${encodeURIComponent(listing.id)}`;
  const exchangeStartPath = `${conversationStartPath}&intent=exchange`;
  const exchangeStartHref = user ? exchangeStartPath : `/login?next=${encodeURIComponent(exchangeStartPath)}`;
  const conversationStartHref = user ? conversationStartPath : `/login?next=${encodeURIComponent(conversationStartPath)}`;
  const location = `${listing.manual_city || listing.city?.name || "Населённый пункт не указан"}, ${listing.region?.name || "Область не указана"}`;
  const powerHp = listing.power_hp ?? listing.modification?.specs?.power_hp;
  const facts = [
    ["Год выпуска", listing.year ? `${listing.year} г.` : "Не указан"],
    ["Пробег", formatMileage(listing.mileage_km)],
    ["Топливо", vehicleLabel(listing.fuel)],
    ["Коробка передач", vehicleLabel(listing.transmission)],
    ["Привод", vehicleLabel(listing.drive)],
    ["Тип кузова", listing.body_type || "Не указан"],
    ...(listing.modification ? [["Модификация", listing.modification.name]] : []),
    ["Двигатель", listing.engine_volume_l ? `${listing.engine_volume_l} л` : "Не указан"],
    ...(powerHp != null ? [["Мощность", `${powerHp.toLocaleString("ru-BY")} л.с.`]] : []),
    ["Состояние", listing.condition === "new" ? "Новый" : listing.condition === "used" ? "С пробегом" : "Не указано"]
  ];
  if (listing.color) facts.push(["Цвет", optionLabels[listing.color] || listing.color]);
  if (listing.customs_status) facts.push(["Таможенный статус", optionLabels[listing.customs_status] || listing.customs_status]);
  if (listing.technical_condition) facts.push(["Техническое состояние", optionLabels[listing.technical_condition] || listing.technical_condition]);
  if (listing.body_condition) facts.push(["Состояние кузова", optionLabels[listing.body_condition] || listing.body_condition]);
  if (listing.district) facts.push(["Район", listing.district]);
  if (listing.call_hours) facts.push(["Время звонков", listing.call_hours]);
  if (listing.equipment?.length) {
    // Onlíner imports retain option IDs but not their values, so those IDs
    // cannot reliably establish which equipment the car actually has.
    const labels = listing.equipment.flatMap((value) => Object.hasOwn(equipmentLabels, value) ? [equipmentLabels[value]] : []);
    const equipment = /^onliner-\d+$/.test(listing.slug) || !labels.length
      ? "Уточняйте комплектацию у продавца"
      : [...new Set(labels)].join(", ") + (labels.length < listing.equipment.length ? ". Остальную комплектацию уточняйте у продавца" : "");
    facts.push(["Комплектация", equipment]);
  }
  const sellerClaims = [
    ...(listing.exchange ? [{ label: "Обмен", value: "Рассматривается" }] : []),
    ...(listing.bargaining ? [{ label: "Торг", value: "Возможен" }] : []),
    ...(listing.credit ? [{ label: "Кредит", value: "Возможен" }] : []),
    ...(listing.leasing ? [{ label: "Лизинг", value: "Возможен" }] : [])
  ];
  const visibleRelatedListings = [...new Map(relatedListings
    .filter((item) => item.id !== listing.id)
    .map((item) => [item.id, item])).values()].slice(0, 8);

  useEffect(() => {
    setSelectedPhotoIndex(0);
  }, [listing.id]);

  useEffect(() => {
    let current = true;
    api.guestContactEnabled().then(({ guest_contact_reveal_enabled }) => {
      if (current) setGuestContactRevealEnabled(guest_contact_reveal_enabled);
    }).catch(() => {
      if (current) setGuestContactRevealEnabled(false);
    });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    let current = true;
    setCanManageActiveListing(false);
    if (listing.status !== "active" || !user) return () => { current = false; };
    api.listingPromotionEligibility(listing.id).then(({ promotable }) => {
      if (!current) return;
      setCanManageActiveListing(promotable);
    }).catch(() => {
      if (current) setCanManageActiveListing(false);
    });
    return () => { current = false; };
  }, [listing.id, listing.seller.id, listing.seller.type, listing.status, user?.id]);

  useEffect(() => {
    setSelectedPhotoIndex((current) => Math.min(current, photos.length - 1));
  }, [photos.length]);

  useEffect(() => {
    const strip = thumbnailsRef.current;
    const selected = strip?.querySelector<HTMLElement>(".is-selected");
    if (!strip || !selected || showAllPhotos) return;
    if (selected.offsetLeft < strip.scrollLeft) strip.scrollLeft = selected.offsetLeft;
    else if (selected.offsetLeft + selected.offsetWidth > strip.scrollLeft + strip.clientWidth) {
      strip.scrollLeft = selected.offsetLeft + selected.offsetWidth - strip.clientWidth;
    }
  }, [safeSelectedPhotoIndex, showAllPhotos]);

  function selectPhoto(index: number) {
    setSelectedPhotoIndex(Math.max(0, Math.min(index, photos.length - 1)));
  }

  function handleGalleryKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (photos.length < 2) return;
    let nextIndex: number | undefined;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (safeSelectedPhotoIndex + 1) % photos.length;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (safeSelectedPhotoIndex - 1 + photos.length) % photos.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = photos.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    selectPhoto(nextIndex);
  }

  async function revealPhone() {
    if (phoneBusy) return;
    setPhoneError("");
    setPhoneBusy(true);
    try {
      const result = await api.revealPhone(listing.id, !user);
      setPhone(result.phone);
      setMessengers(result.messengers ?? []);
      setContactsRevealed(true);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) router.push(`/login?next=${encodeURIComponent(href)}`);
      else if (error instanceof ApiClientError && error.status === 429) setPhoneError("Слишком много запросов на показ телефона. Попробуйте позже или напишите продавцу.");
      else setPhoneError(error instanceof Error ? error.message : "Не удалось показать контакт");
    } finally {
      setPhoneBusy(false);
    }
  }

  function recordContactClick(channel: ContactChannel) {
    void trackContactClick({ listingId: listing.id, channel, consent });
  }

  return (
    <div className="page-width detail-page">
      <nav className="breadcrumb" aria-label="Хлебные крошки">
        <Link href="/">Главная</Link><ChevronRight size={14} /><Link href="/cars">Автомобили</Link>
        {listingCatalogBreadcrumbs(listing).map((item) => <Fragment key={item.path}><ChevronRight size={14} /><Link href={item.path}>{item.name}</Link></Fragment>)}
      </nav>
      <div className="detail-layout">
        <div className="detail-main-column">
          <div className="detail-gallery" role="region" aria-label={`Фотографии автомобиля «${listing.title}»`} tabIndex={0} onKeyDown={handleGalleryKeyDown}>
            <div className="detail-photo-wrap">
              <Image id="detail-main-image" className="detail-main-image" src={selectedPhoto} alt={hasSyntheticPhoto ? `Синтетическое изображение для объявления «${listing.title}»` : listingPhotoAlt(listing.title, safeSelectedPhotoIndex + 1)} width={1448} height={1086} sizes="(max-width: 800px) calc(100vw - 28px), min(792px, 62vw)" priority />
              {hasSyntheticPhoto && <span className="synthetic-label detail-synthetic-label">Синтетическое фото</span>}
              {!hasSyntheticPhoto && <ListingPhotoBadges badges={listing.photo_badges} />}
              {photos.length > 1 && <>
                <button className="detail-photo-arrow detail-photo-arrow-prev" type="button" aria-label="Предыдущее фото" aria-controls="detail-main-image" onClick={() => selectPhoto((safeSelectedPhotoIndex - 1 + photos.length) % photos.length)}><ChevronLeft aria-hidden="true" /></button>
                <button className="detail-photo-arrow detail-photo-arrow-next" type="button" aria-label="Следующее фото" aria-controls="detail-main-image" onClick={() => selectPhoto((safeSelectedPhotoIndex + 1) % photos.length)}><ChevronRight aria-hidden="true" /></button>
              </>}
            </div>
            {photos.length > 1 && <>
              <div ref={thumbnailsRef} id="detail-photo-list" className={`detail-thumbnails${showAllPhotos ? " detail-thumbnails-expanded" : ""}`} role="group" aria-label="Выбор фотографии">{photos.map((photo, index) => <button className={`detail-thumbnail ${index === safeSelectedPhotoIndex ? "is-selected" : ""}`} key={`${photo}-${index}`} type="button" aria-current={index === safeSelectedPhotoIndex ? "true" : undefined} aria-label={`Показать фото ${index + 1} из ${photos.length}`} aria-controls="detail-main-image" onClick={() => selectPhoto(index)}><Image src={photo} alt={listingPhotoAlt(listing.title, index + 1)} width={360} height={270} sizes="(max-width: 520px) calc((100vw - 48px) / 4), (max-width: 800px) 20vw, 16vw" /></button>)}</div>
              <button className="detail-photos-toggle" type="button" aria-expanded={showAllPhotos} aria-controls="detail-photo-list" onClick={() => setShowAllPhotos((current) => !current)}>{showAllPhotos ? "Свернуть фотографии" : `Показать все фото (${photos.length})`}</button>
            </>}
          </div>
          <section className="detail-summary section">
            <h1 className="detail-title">{listing.title}</h1>
            {listing.in_transit && <p className="status-pill">Авто в пути · указано продавцом</p>}
            <p className="muted location-line"><MapPin size={15} aria-hidden="true" /> {location} · добавлено {formatDate(listing.created_at)} {listing.view_count != null && <span className="listing-views" role="img" aria-label={`Просмотры: ${listing.view_count}`}><Eye size={15} aria-hidden="true" /> {listing.view_count.toLocaleString("ru-BY")}</span>}</p>
            <h2>Характеристики</h2>
            <div className="detail-facts">{facts.map(([name, value]) => <div className="detail-fact" key={name}><span>{name}</span><strong>{value}</strong></div>)}</div>
            {listing.damaged && <p className="notice">Продавец указал повреждения.</p>}
            {listing.parts_only && <p className="notice">Продаётся на запчасти.</p>}
          </section>
          <ListingTrust claims={sellerClaims} evidence={listing.verified_evidence || []} />
          <section className="detail-summary">
            <h2>Описание</h2>
            <p className="detail-description">{listing.description || "Продавец не добавил описание."}</p>
          </section>
        </div>
        <aside className="detail-panel" aria-label="Цена и продавец">
          {listing.status === "sold" && <p className="status-pill">Продано</p>}
          <div className="detail-price-row">
            <p className="detail-price">{formatMoney(listing.price)}</p>
            <PriceConversions price={listing.price} />
          </div>
          {listing.price?.currency === "USD" && listing.price.display_byn && listing.price.rate_date && <p className="muted">В BYN по курсу на {formatDate(listing.price.rate_date)}</p>}
          <Link className="button button-secondary ownership-calculator-link" href={`/ownership-calculator?listing=${encodeURIComponent(listing.id)}`}>Рассчитать стоимость владения</Link>
          {listing.status === "active" ? <>
            {(listing.has_phone !== false || listing.has_external_contacts === true) ? <ListingContactActions active={true} guestContactRevealEnabled={!user && guestContactRevealEnabled} revealed={contactsRevealed} phone={phone} busy={phoneBusy} error={phoneError} onReveal={() => { void revealPhone(); }} messengers={messengers} onContactClick={recordContactClick} /> : <p className="muted">Продавец предпочитает общаться в переписке.</p>}
            {user?.id !== listing.seller.id && <Link className={`button ${listing.has_phone === false && !listing.has_external_contacts ? "button-primary" : "button-secondary"} contact-chat`} href={conversationStartHref} onClick={() => recordContactClick("internal_chat")}><MessageCircle size={17} aria-hidden="true" /> Написать продавцу</Link>}
            {listing.exchange && user?.id !== listing.seller.id && <Link className="button button-secondary exchange-offer" href={exchangeStartHref}>Предложить обмен</Link>}
          </> : <ListingContactActions active={false} guestContactRevealEnabled={false} phone="" busy={false} error="" onReveal={() => undefined} />}
          <FavoriteButton listingId={listing.id} href={href} initialSaved={initialSaved} />
          {canManageActiveListing && <Link className="button button-secondary contact-chat" href={`/account/billing?listing_id=${encodeURIComponent(listing.id)}`}>Услуги продвижения</Link>}
          <div className="detail-actions">
            <ComparisonAction listingId={listing.id} />
            <ShareButton href={href} title={listing.title} />
          </div>
          <div className="seller-box">
            <span className={`seller-tag ${listing.seller.type === "private" ? "private" : ""}`}>
              {listing.seller.type === "company" ? <Building2 size={16} /> : <CircleUserRound size={16} />}
              {listing.seller.type === "company" ? "Компания" : "Частный продавец"}
            </span>
            {listing.seller.type === "company" && listing.seller.slug ? <p><Link className="text-link" href={`/dealers/${encodeURIComponent(listing.seller.slug)}`} onClick={() => { void api.trackDealerClick(listing.id).catch(() => undefined); }}>{listing.seller.name} <ChevronRight size={15} /></Link></p> : <p><strong>{listing.seller.name}</strong></p>}
            <p className="muted">{location}</p>
          </div>
          <ReportForm listingId={listing.id} href={href} />
          {listing.status === "active" && <p className="privacy-note"><ShieldCheck size={15} /> {listing.has_phone === false && !listing.has_external_contacts ? "Продавец может поделиться контактом в переписке." : "Контакты открываются по запросу и не показываются в публичной выдаче."}</p>}
        </aside>
      </div>
      {visibleRelatedListings.length > 0 && <section className="related-listings section" aria-labelledby="related-listings-heading"><div className="section-heading"><h2 id="related-listings-heading">Похожие объявления</h2></div><div className="listing-stack">{visibleRelatedListings.map((item) => <ListingCard key={item.id} listing={item} variant="row" />)}</div></section>}
      <SellerListings listingId={listing.id} sellerId={listing.seller.id} items={sellerListings} />
      {listing.status === "active" && <ListingPriceHistory listingId={listing.id} />}
      <RecentlyViewedListings currentListingId={listing.id} userId={user?.id ?? null} shouldRecord={listing.status === "active"} />
    </div>
  );
}

function ReportForm({ listingId, href }: { listingId: string; href: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setStatus("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const selectedCategory = String(form.get("category") || "");
    const category = reportCategories.find((item) => item.value === selectedCategory)?.value;
    if (!category) {
      setError("Выберите причину жалобы.");
      return;
    }
    setBusy(true);
    try {
      await api.createReport(listingId, { category, comment: String(form.get("comment") || "") });
      setStatus("Жалоба отправлена на проверку.");
      formElement.reset();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.push(`/login?next=${encodeURIComponent(href)}`);
      else setError(issue instanceof Error ? issue.message : "Не удалось отправить жалобу");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="report-form">
      <summary><AlertTriangle size={14} /> Пожаловаться на объявление</summary>
      <form onSubmit={submit}>
        <label className="field"><span>Причина</span><select name="category" required defaultValue=""><option value="" disabled>Выберите причину</option>{reportCategories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}</select></label>
        <label className="field"><span>Комментарий</span><textarea name="comment" maxLength={2000} placeholder="Опишите проблему" /></label>
        <button className="button button-secondary" type="submit" disabled={busy} aria-busy={busy}><AlertTriangle size={15} /> {busy ? "Отправляем…" : "Отправить жалобу"}</button>
        {status && <p className="inline-success" role="status">{status}</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
      </form>
    </details>
  );
}
