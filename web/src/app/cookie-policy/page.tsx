import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import { PublishedLegalDocument } from "@/components/published-legal-document";
import { loadApprovedLegalDocument } from "@/lib/legal-documents";

export const metadata: Metadata = { title: "Политика cookie" };

export default async function CookiePolicyPage() {
  const approved = await loadApprovedLegalDocument("cookie_policy");
  if (approved) return <PublishedLegalDocument document={approved} />;
  return (
    <InformationalPage
      eyebrow="Документ"
      title="Политика cookie"
      description="Проект описания cookies и похожих технических средств в закрытом пилоте."
      notice="ПРОЕКТ / ЧЕРНОВИК. Набор доменов, оператор и сроки хранения должны быть подтверждены перед публичным запуском."
    >
      <section className="info-section">
        <h2>Какие cookie используются</h2>
        <div className="info-table-wrap">
          <table className="info-table">
            <thead><tr><th>Cookie</th><th>Назначение</th><th>Срок</th></tr></thead>
            <tbody>
              <tr><td><code>avtorinok_session</code></td><td>Серверная авторизация; HttpOnly, Secure в HTTPS-пилоте, SameSite=Lax.</td><td>До 7 дней</td></tr>
              <tr><td><code>avtorinok_csrf</code></td><td>CSRF-защита изменяющих состояние запросов; не HttpOnly, чтобы клиент мог передать токен в заголовке.</td><td>До 7 дней</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section className="info-section">
        <h2>Защита контактов в публичном режиме</h2>
        <p>В закрытом пилоте этот режим выключен. Если оператор отдельно включает показ телефона гостям, используются только технические cookie для защиты запросов и ограничения массового сбора контактов.</p>
        <ul className="info-list">
          <li><code>avtorinok_guest_contact_device</code> — подписанный случайный идентификатор для ограничения запросов, срок 24 часа.</li>
          <li><code>avtorinok_guest_contact_proof</code> — доказательство запроса из интерфейса сайта, срок 15 минут.</li>
        </ul>
        <p>Обе cookie — HttpOnly и SameSite=Strict, Secure при HTTPS. В cookie нет телефона или IP-адреса. При выключенном режиме новые cookie этого вида не создаются. Перед публичным включением оператор утверждает актуальную версию политики.</p>
      </section>
      <section className="info-section">
        <h2>Чего нет в пилоте</h2>
        <p>Пилот не заявляет рекламных, аналитических или сторонних tracking-cookie. Браузер может хранить собственные технические данные; их состав зависит от настроек устройства и не является частью сервиса.</p>
      </section>
      <section className="info-section">
        <h2>Управление и вопросы</h2>
        <p>Удаление cookie обычно завершает локальную сессию, но не удаляет серверную учётную запись. Для завершения сеанса используйте кнопку «Выйти». Порядок удаления серверных записей и контакт оператора будут добавлены в утверждённую версию документа.</p>
      </section>
    </InformationalPage>
  );
}
