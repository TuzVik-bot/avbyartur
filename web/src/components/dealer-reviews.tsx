"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { api } from "@/lib/api";
import type { DealerReview, DealerReviewPrivate, DealerReviews as DealerReviewsData } from "@/lib/types";
import styles from "./dealer-reviews.module.css";

const statusLabels: Record<DealerReviewPrivate["status"], string> = {
  pending: "На проверке",
  published: "Опубликован",
  rejected: "Возвращён на доработку",
  hidden: "Скрыт модератором"
};

export function DealerReviews({ slug, reviews }: { slug: string; reviews: DealerReviewsData | undefined }) {
  const { user } = useAuth();
  const [mine, setMine] = useState<DealerReviewPrivate | null>(null);
  const [rating, setRating] = useState(5);
  const [reviewText, setReviewText] = useState("");
  const [reportId, setReportId] = useState("");
  const [reportReason, setReportReason] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) {
      setMine(null);
      return;
    }
    let alive = true;
    api.myDealerReview(slug).then(({ review }) => {
      if (!alive) return;
      setMine(review);
      if (review) {
        setRating(review.rating);
        setReviewText(review.text);
      }
    }).catch(() => {
      if (alive) setError("Не удалось загрузить ваш отзыв.");
    });
    return () => { alive = false; };
  }, [slug, user]);

  async function submitReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const data = { rating, text: reviewText };
      const result = mine
        ? await api.updateDealerReview(mine.id, { ...data, expected_revision: mine.revision })
        : await api.createDealerReview(slug, data);
      setMine(result.review);
      setRating(result.review.rating);
      setReviewText(result.review.text);
      setMessage("Отзыв отправлен на проверку модератору.");
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось сохранить отзыв.");
    } finally {
      setBusy(false);
    }
  }

  async function submitReport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.reportDealerReview(reportId, reportReason);
      setMessage("Жалоба отправлена модератору.");
      setReportId("");
      setReportReason("");
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось отправить жалобу.");
    } finally {
      setBusy(false);
    }
  }

  const items: DealerReview[] = reviews?.items || [];
  const loginPath = `/login?next=${encodeURIComponent(`/dealers/${slug}`)}`;
  return (
    <section className={`section ${styles.reviews}`} aria-labelledby="dealer-reviews-title">
      <div className="section-heading">
        <h2 id="dealer-reviews-title">Отзывы о компании</h2>
        {reviews && reviews.count > 0 && <span className={styles.rating} aria-label={`Средняя оценка ${reviews.average_rating} из 5`}><strong>{reviews.average_rating?.toFixed(2)}</strong> / 5 · {reviews.count} отзывов</span>}
      </div>
      {!reviews || reviews.count === 0 ? <p className="muted" role="status">Отзывов пока нет.</p> : (
        <ul className={styles.reviewList}>
          {items.map((review) => <li key={review.id} className={styles.review}>
            <p className={styles.stars} aria-label={`Оценка ${review.rating} из 5`}>{"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}</p>
            <p>{review.text}</p>
            <time dateTime={review.created_at}>{new Date(review.created_at).toLocaleDateString("ru-RU")}</time>
            {user && review.id !== mine?.id && <button type="button" className="text-link" onClick={() => setReportId(review.id)}>Пожаловаться</button>}
            {reportId === review.id && <form className={styles.reportForm} onSubmit={submitReport}>
              <label>Причина жалобы<textarea value={reportReason} maxLength={1000} required onChange={(event) => setReportReason(event.currentTarget.value)} /></label>
              <button className="button button-secondary button-small" disabled={busy}>Отправить жалобу</button>
              <button className="button button-secondary button-small" type="button" onClick={() => setReportId("")}>Отмена</button>
            </form>}
          </li>)}
        </ul>
      )}
      <p className={styles.disclaimer}>Отзывы оставляют авторизованные пользователи. Факт покупки не подтверждается.</p>
      {user ? <form className={styles.reviewForm} onSubmit={submitReview}>
        <h3>{mine ? "Ваш отзыв" : "Оставить отзыв"}</h3>
        {mine && <p className="muted" role="status">Статус: {statusLabels[mine.status]}.{mine.moderation_reason ? ` ${mine.moderation_reason}` : ""}</p>}
        <label>Оценка<select value={rating} onChange={(event) => setRating(Number(event.currentTarget.value))}>{[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} из 5</option>)}</select></label>
        <label>Текст отзыва<textarea value={reviewText} maxLength={2000} required onChange={(event) => setReviewText(event.currentTarget.value)} /></label>
        <button className="button button-primary button-small" disabled={busy}>{busy ? "Сохраняем…" : mine ? "Сохранить изменения" : "Отправить на проверку"}</button>
      </form> : <p><Link href={loginPath}>Войдите, чтобы оставить отзыв</Link></p>}
      {message && <p role="status">{message}</p>}
      {error && <p className="notice" role="alert">{error}</p>}
    </section>
  );
}
