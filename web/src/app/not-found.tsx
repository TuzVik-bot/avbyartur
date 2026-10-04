import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Страница не найдена",
  robots: { index: false, follow: false }
};

export default function NotFound() {
  return (
    <div className="page-width not-found-state">
      <p className="eyebrow">Авторынок</p>
      <h1>Страница не найдена</h1>
      <p className="muted">Проверьте адрес или откройте каталог автомобилей, чтобы продолжить поиск.</p>
      <div className="error-actions">
        <Link className="button button-primary" href="/cars">К автомобилям</Link>
        <Link className="button button-secondary" href="/">На главную</Link>
      </div>
    </div>
  );
}
