"use client";

import { Share2 } from "lucide-react";
import { useState } from "react";

type ShareButtonProps = { href: string; title: string };

export function ShareButton({ href, title }: ShareButtonProps) {
  const [status, setStatus] = useState("");

  async function share() {
    setStatus("");
    const url = new URL(href, window.location.origin).href;
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        setStatus("Ссылка отправлена.");
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setStatus("Не удалось поделиться ссылкой.");
      }
      return;
    }
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(url);
      setStatus("Ссылка скопирована.");
    } catch {
      setStatus("Не удалось скопировать ссылку. Скопируйте адрес из строки браузера.");
    }
  }

  return <span className="share-action">
    <button className="button button-secondary button-small" type="button" onClick={() => void share()}><Share2 size={16} aria-hidden="true" /> Поделиться</button>
    <span role="status" aria-live="polite">{status}</span>
  </span>;
}
