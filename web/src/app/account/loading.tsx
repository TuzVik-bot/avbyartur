export default function AccountLoading() {
  return (
    <div className="page-width route-loading" aria-busy="true" aria-label="Загрузка кабинета">
      <header className="page-head">
        <p className="eyebrow">Личный кабинет</p>
        <h1>Загружаем кабинет…</h1>
        <p>Получаем объявления, избранное и настройки профиля.</p>
      </header>
      <div className="account-nav account-nav-loading" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="route-skeleton account-loading-skeleton" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="sr-only" role="status">Загружаем данные кабинета…</p>
    </div>
  );
}
