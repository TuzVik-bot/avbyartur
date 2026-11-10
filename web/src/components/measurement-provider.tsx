"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { DEFAULT_GA_MEASUREMENT_ID, isAnalyticsExcludedPath } from "./analytics-consent-config";
import { useContactClickConsent } from "./contact-click-consent";
import { measurementReady, setMeasurementConsent, setMeasurementEnabled, subscribeMeasurementReady, trackFunnelEvent, type FunnelEventPayloads } from "@/lib/funnel-analytics";

export function MeasurementProvider({ children, measurementId = DEFAULT_GA_MEASUREMENT_ID }: { children: React.ReactNode; measurementId?: string }) {
  const { consent } = useContactClickConsent();
  const pathname = usePathname() ?? "/";
  // Private sections (account, admin, auth tokens) are never measured, even with consent.
  const active = consent === "granted" && !isAnalyticsExcludedPath(pathname);
  useEffect(() => {
    setMeasurementEnabled(false);
    setMeasurementConsent(active);
    if (!active) return;
    const flags = window as unknown as Record<string, unknown>;
    let script: HTMLScriptElement | undefined;
    const denied = { analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" };
    try {
      flags[`ga-disable-${measurementId}`] = false;
      window.dataLayer = [];
      // gtag.js only accepts the Arguments object, not a rest-parameter array.
      // eslint-disable-next-line prefer-rest-params
      window.gtag = function () { window.dataLayer?.push(arguments); };
      window.gtag("consent", "default", denied);
      window.gtag("consent", "update", { analytics_storage: "granted" });
      window.gtag("js", new Date());
      window.gtag("config", measurementId, { send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false, page_location: window.location.origin, page_title: "Avtorinok", page_referrer: "" });
      script = document.createElement("script");
      script.async = true;
      script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
      script.onerror = () => {
        setMeasurementEnabled(false);
        flags[`ga-disable-${measurementId}`] = true;
        window.dataLayer?.splice(0);
      };
      document.head.appendChild(script);
      setMeasurementEnabled(true);
    } catch {
      setMeasurementEnabled(false);
      flags[`ga-disable-${measurementId}`] = true;
      script?.remove();
      window.dataLayer?.splice(0);
      delete window.gtag;
    }
    return () => {
      setMeasurementEnabled(false);
      setMeasurementConsent(false);
      flags[`ga-disable-${measurementId}`] = true;
      if (script) { script.onload = null; script.onerror = null; script.remove(); }
      try { window.gtag?.("consent", "update", denied); } catch { /* Measurement cannot block the UI. */ }
      window.dataLayer?.splice(0);
      delete window.gtag;
    };
  }, [active, measurementId]);
  return <>{children}</>;
}

/** Records the current view once per identity and consent period; it never buffers pre-consent history. */
export function useMeasurementView<E extends "listing_opened" | "search_results_viewed">(name: E, payload: FunnelEventPayloads[E], viewKey: string) {
  const ready = useSyncExternalStore(subscribeMeasurementReady, measurementReady, () => false);
  const lastView = useRef<string | null>(null);
  useEffect(() => {
    if (!ready) { lastView.current = null; return; }
    const key = JSON.stringify([name, viewKey]);
    if (lastView.current !== key && trackFunnelEvent(name, payload)) lastView.current = key;
  }, [ready, name, viewKey, payload]);
}
