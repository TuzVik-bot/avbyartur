/**
 * App Router fallback for routes that do not have a more specific loading UI.
 * Keep this state useful on a slow API: the shell stays visible and the message
 * explains what is happening without implying that the request succeeded.
 */
export default function AppLoading() {
  return (
    <div className="page-width route-loading" aria-busy="true" aria-label="Загрузка страницы">
      <div className="route-skeleton app-loading-skeleton" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="sr-only" role="status">Загружаем страницу…</p>
    </div>
  );
}
