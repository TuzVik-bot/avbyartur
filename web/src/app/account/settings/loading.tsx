export default function AccountSettingsLoading() {
  return (
    <div className="page-width route-loading" aria-busy="true" aria-label="Загрузка настроек аккаунта">
      <header className="page-head">
        <p className="eyebrow">Личный кабинет</p>
        <h1>Загружаем настройки…</h1>
        <p>Получаем список активных сеансов.</p>
      </header>
      <div className="route-skeleton account-loading-skeleton" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="sr-only" role="status">Загружаем активные сеансы…</p>
    </div>
  );
}
