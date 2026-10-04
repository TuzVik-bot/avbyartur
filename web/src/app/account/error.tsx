"use client";

import { useEffect } from "react";
import Link from "next/link";

type AccountErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function AccountError({ error, reset }: AccountErrorProps) {
  useEffect(() => {
    // Keep the boundary visible to the operator without exposing the digest in
    // the page, where it could be mistaken for an actionable support token.
    console.error("Account route failed", error);
  }, [error]);

  return (
    <div className="page-width error-state" role="alert">
      <p className="eyebrow">Личный кабинет</p>
      <h1>Не удалось открыть раздел кабинета</h1>
      <p className="muted">Сервис вернул ошибку. Повторите попытку или вернитесь к обзору кабинета.</p>
      <div className="error-actions">
        <button className="button button-primary" type="button" onClick={() => reset()}>Повторить</button>
        <Link className="button button-secondary" href="/account">В кабинет</Link>
      </div>
    </div>
  );
}
