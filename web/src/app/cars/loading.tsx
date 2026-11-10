/**
 * Loading UI for the car search, catalog landings and listing pages.
 * Mirrors the root loading state so a slow API keeps the shell visible
 * without implying that the listings already arrived.
 */
export default function CarsLoading() {
  return (
    <div className="page-width route-loading" aria-busy="true" role="group" aria-label="Загрузка объявлений">
      <div className="route-skeleton" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <p className="sr-only" role="status">Загружаем объявления…</p>
    </div>
  );
}
