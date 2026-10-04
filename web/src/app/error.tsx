"use client";

import { useEffect } from "react";
import Link from "next/link";

type AppErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function AppError({ error, reset }: AppErrorProps) {
  useEffect(() => {
    console.error("Route failed", error);
  }, [error]);

  return (
    <div className="page-width error-state" role="alert">
      <p className="eyebrow">Авторынок</p>
      <h1>Страница временно недоступна</h1>
      <p className="muted">Попробуйте повторить загрузку. Если ошибка не исчезнет, вернитесь к поиску автомобилей.</p>
      <div className="error-actions">
        <button className="button button-primary" type="button" onClick={() => reset()}>Повторить</button>
        <Link className="button button-secondary" href="/cars">К поиску автомобилей</Link>
      </div>
    </div>
  );
}
