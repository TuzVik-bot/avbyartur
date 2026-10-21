"use client";

import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";
import styles from "./install-prompt.module.css";

type DeferredInstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

function isStandaloneDisplay(): boolean {
  return (typeof window.matchMedia === "function" && window.matchMedia("(display-mode: standalone)").matches) ||
    ("standalone" in navigator && Boolean((navigator as Navigator & { standalone?: boolean }).standalone));
}

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<DeferredInstallPrompt | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (isStandaloneDisplay()) return;

    function onBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      setDeferredPrompt(event as DeferredInstallPrompt);
    }

    function onAppInstalled() {
      setDeferredPrompt(null);
    }

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  if (!deferredPrompt || dismissed) return null;

  function requestInstall() {
    const event = deferredPrompt;
    if (!event) return;
    setDeferredPrompt(null);
    void event.prompt().then(() => event.userChoice).catch(() => undefined);
  }

  return (
    <aside className={styles.root} aria-label="Установить приложение">
      <div className={styles.copy}>
        <strong>Авторынок BY</strong>
        <p>Добавьте каталог на главный экран для быстрого доступа.</p>
      </div>
      <button className={styles.install} type="button" data-install-action="install" onClick={requestInstall}>
        <Download size={17} aria-hidden="true" />
        Установить
      </button>
      <button className={styles.dismiss} type="button" data-install-action="dismiss" aria-label="Скрыть приглашение" onClick={() => setDismissed(true)}>
        <X size={18} aria-hidden="true" />
      </button>
    </aside>
  );
}
