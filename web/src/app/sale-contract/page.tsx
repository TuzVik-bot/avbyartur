import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import styles from "./sale-contract.module.css";

export const metadata: Metadata = {
  title: "Договор купли-продажи",
  description: "Раздел договора купли-продажи автомобиля на Авторынке."
};

export default function SaleContractPage() {
  return (
    <InformationalPage
      eyebrow="Сервисы"
      title="Договор купли-продажи"
      description="Пример заполнения договора купли-продажи автомобиля."
      notice={<><strong>Образец · Все данные вымышлены.</strong> Пример предназначен для демонстрации раздела. Это не готовый документ для подписания.</>}
    >
      <section className="info-section" aria-labelledby="sale-contract-template">
        <p className="eyebrow">Демонстрационный договор № ОБРАЗЕЦ-001</p>
        <h2 id="sale-contract-template">Договор купли-продажи автомобиля</h2>
        <p>г. Минск · 13 октября 2026 года</p>
      </section>
      <section className="info-section" aria-labelledby="sale-contract-parties">
        <h2 id="sale-contract-parties">1. Продавец и покупатель</h2>
        <div className={styles.parties}>
          <div className="info-card">
            <h3>Продавец</h3>
            <p><strong>Иванов Иван Иванович</strong></p>
            <p>Документ: ОБРАЗЕЦ-ПРОДАВЕЦ</p>
            <p>Адрес: г. Минск, ул. Вымышленная, д. 10, кв. 5</p>
          </div>
          <div className="info-card">
            <h3>Покупатель</h3>
            <p><strong>Петрова Анна Сергеевна</strong></p>
            <p>Документ: ОБРАЗЕЦ-ПОКУПАТЕЛЬ</p>
            <p>Адрес: г. Минск, ул. Примерная, д. 20, кв. 15</p>
          </div>
        </div>
      </section>
      <section className="info-section" aria-labelledby="sale-contract-car">
        <h2 id="sale-contract-car">2. Автомобиль</h2>
        <dl className={styles.details}>
          <div><dt>Марка и модель</dt><dd>Volkswagen Passat</dd></div>
          <div><dt>Год выпуска</dt><dd>2018</dd></div>
          <div><dt>Цвет</dt><dd>Серебристый</dd></div>
          <div><dt>VIN</dt><dd>DEMO-VIN-ОБРАЗЕЦ (не настоящий VIN)</dd></div>
          <div><dt>Регистрационный знак</dt><dd>ОБРАЗЕЦ-001</dd></div>
          <div><dt>Свидетельство о регистрации</dt><dd>ОБРАЗЕЦ-ТЕХПАСПОРТ</dd></div>
          <div><dt>Пробег</dt><dd>125 000 км</dd></div>
        </dl>
      </section>
      <section className="info-section" aria-labelledby="sale-contract-payment">
        <h2 id="sale-contract-payment">3. Цена и расчёт</h2>
        <p>Цена автомобиля в примере: <strong>25 000 BYN</strong> (двадцать пять тысяч белорусских рублей).</p>
        <p>Способ расчёта в примере: банковский перевод в день передачи автомобиля, 13 октября 2026 года.</p>
      </section>
      <section className="info-section" aria-labelledby="sale-contract-handover">
        <h2 id="sale-contract-handover">4. Передача автомобиля</h2>
        <p>Место и дата в примере: г. Минск, 13 октября 2026 года.</p>
        <p>Комплект передачи в примере: автомобиль, два ключа, свидетельство о регистрации и сервисная книжка.</p>
      </section>
      <section className="info-section" aria-labelledby="sale-contract-signatures">
        <h2 id="sale-contract-signatures">5. Подписи сторон</h2>
        <div className={styles.parties}>
          <p>Продавец: Иванов И. И.<br /><span className="muted">Подпись отсутствует · Образец</span></p>
          <p>Покупатель: Петрова А. С.<br /><span className="muted">Подпись отсутствует · Образец</span></p>
        </div>
      </section>
    </InformationalPage>
  );
}
