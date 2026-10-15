"use client";

import { useEffect } from "react";
import Link from "next/link";
import { reportFrontendError, type FrontendErrorType } from "@/lib/analytics";

type CarsErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function CarsError({ error, reset }: CarsErrorProps) {
  useEffect(() => {
    console.error("Cars route failed");
    void reportFrontendError({
      errorType: error.name as FrontendErrorType,
      releaseId: process.env.NEXT_PUBLIC_RELEASE_ID ?? "",
      breadcrumbs: [],
    });
  }, [error]);

  return (
    <div className="page-width error-state" role="alert">
      <p className="eyebrow">Поиск автомобилей</p>
      <h1>Не удалось загрузить поиск</h1>
      <p className="muted">Фильтры и объявления временно недоступны. Повторите запрос или начните с главной страницы.</p>
      <div className="error-actions">
        <button className="button button-primary" type="button" onClick={() => reset()}>Повторить</button>
        <Link className="button button-secondary" href="/">На главную</Link>
      </div>
    </div>
  );
}
