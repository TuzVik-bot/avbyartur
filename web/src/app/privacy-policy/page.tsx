import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import { PublishedLegalDocument } from "@/components/published-legal-document";
import { loadApprovedLegalDocument } from "@/lib/legal-documents";

export const metadata: Metadata = { title: "Политика конфиденциальности" };

export default async function PrivacyPolicyPage() {
  const approved = await loadApprovedLegalDocument("privacy_policy");
  if (approved) return <PublishedLegalDocument document={approved} />;
  return (
    <InformationalPage
      eyebrow="Документ"
      title="Политика конфиденциальности"
      description="Проект описания обработки данных в закрытом пилоте."
      notice="ПРОЕКТ / ЧЕРНОВИК. Не является утверждённой политикой обработки персональных данных. Оператор, реквизиты, сроки хранения и юридические основания должны быть заполнены владельцем сервиса."
    >
      <section className="info-section">
        <h2>Какие данные используются</h2>
        <ul className="info-list">
          <li>данные учётной записи: email, отображаемое имя и роль;</li>
          <li>данные объявления: сведения об автомобиле, цена, местоположение, описание, VIN и контактный телефон, если участник их указал;</li>
          <li>фотографии и технические статусы их обработки;</li>
          <li>технические записи сессии, CSRF-защиты, действий кабинета и модерации.</li>
        </ul>
      </section>
      <section className="info-section">
        <h2>Для чего это нужно</h2>
        <p>Данные используются для входа, сохранения черновиков, показа опубликованных объявлений, премодерации, защиты от подделки запросов и расследования жалоб. Телефон исключён из публичной выдачи: для просмотра применяется отдельный защищённый запрос.</p>
      </section>
      <section className="info-section">
        <h2>Доступ и защита</h2>
        <p>Сессия хранится на сервере. Сессионная cookie помечена HttpOnly, а состояние cookie в рабочем HTTPS-режиме — Secure и SameSite=Lax; CSRF-токен нужен для изменяющих состояние запросов. Фото хранятся в приватном хранилище и выдаются только после проверки доступа.</p>
      </section>
      <section className="info-section">
        <h2>Что требуется уточнить до запуска</h2>
        <p>Владелец должен добавить категории данных, получателей, сроки хранения и удаления, права участника, порядок отзыва согласия/запросов и канал связи. В этом черновике нет выдуманных имен, адресов и email.</p>
      </section>
    </InformationalPage>
  );
}
