"use client";

import { useEffect } from "react";
import Link from "next/link";

type DealersErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function DealersError({ error, reset }: DealersErrorProps) {
  useEffect(() => {
    console.error("Dealer directory route failed", error);
  }, [error]);

  return (
    <div className="page-width error-state" role="alert">
      <p className="eyebrow">Автокомпании</p>
      <h1>Не удалось открыть список компаний</h1>
      <p className="muted">Проверьте соединение и повторите попытку. Если проблема сохраняется, откройте поиск автомобилей.</p>
      <div className="error-actions">
        <button className="button button-primary" type="button" onClick={() => reset()}>Повторить</button>
        <Link className="button button-secondary" href="/cars">К поиску автомобилей</Link>
      </div>
    </div>
  );
}
