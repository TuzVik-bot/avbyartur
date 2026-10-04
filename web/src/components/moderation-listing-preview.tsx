import { formatMileage, formatMoney, vehicleLabel } from "@/lib/format";
import type { Listing } from "@/lib/types";

export function ModerationListingPreview({ listing }: { listing: Listing }) {
  const location = `${listing.manual_city || listing.city?.name || "Населённый пункт не указан"}, ${listing.region?.name || "Область не указана"}`;
  const photos = listing.photos || listing.photo_urls.map((url, index) => ({
    id: `${listing.id}-photo-${index}`,
    url,
    status: "ready",
    position: index,
    is_cover: index === 0
  }));

  return (
    <details className="moderation-preview">
      <summary>Посмотреть сведения</summary>
      <dl>
        <div><dt>Автомобиль</dt><dd>{[listing.make?.name, listing.model?.name].filter(Boolean).join(" ") || listing.title || "Марка и модель не выбраны"}{listing.generation ? ` · ${listing.generation.name}` : ""}</dd></div>
        <div><dt>Год и пробег</dt><dd>{listing.year ? `${listing.year} г.` : "Год не указан"} · {formatMileage(listing.mileage_km)}</dd></div>
        <div><dt>Цена</dt><dd>{formatMoney(listing.price)}</dd></div>
        <div><dt>Расположение</dt><dd>{location}</dd></div>
        <div><dt>Топливо</dt><dd>{vehicleLabel(listing.fuel)}</dd></div>
        <div><dt>Коробка и привод</dt><dd>{vehicleLabel(listing.transmission)} · {vehicleLabel(listing.drive)}</dd></div>
        <div><dt>Состояние</dt><dd>{listing.condition === "new" ? "Новый" : "С пробегом"}{listing.damaged ? " · повреждения" : ""}{listing.parts_only ? " · на запчасти" : ""}</dd></div>
        {listing.body_type && <div><dt>Тип кузова</dt><dd>{listing.body_type}</dd></div>}
        {listing.engine_volume_l && <div><dt>Объём двигателя</dt><dd>{listing.engine_volume_l} л</dd></div>}
        {listing.power_hp && <div><dt>Мощность</dt><dd>{listing.power_hp} л.с.</dd></div>}
      </dl>
      <section>
        <h3>Описание</h3>
        <p>{listing.description || "Описание не добавлено."}</p>
      </section>
      <section>
        <h3>Фотографии ({photos.length})</h3>
        {photos.length ? <div className="moderation-preview-photos">
          {photos.map((photo, index) => photo.url
            ? <img key={photo.id} src={photo.url} alt={photo.is_cover ? "Обложка объявления" : `Фото ${index + 1}`} loading="lazy" />
            : <span className="muted" key={photo.id}>Фото {index + 1}: {photo.status === "failed" ? "ошибка обработки" : "обрабатывается"}</span>)}
        </div> : <p>Фотографии не добавлены.</p>}
      </section>
    </details>
  );
}
