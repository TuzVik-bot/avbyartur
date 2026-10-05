import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SiteFooter } from "@/components/site-footer";

const requiredContentLinks = {
  "/about": { group: "Информация", label: "О нас" },
  "/faq": { group: "Информация", label: "Часто задаваемые вопросы" },
  "/support": { group: "Информация", label: "Служба поддержки" },
  "/vin-check": { group: "Сервисы", label: "Проверка транспорта по VIN" },
  "/financing": { group: "Сервисы", label: "Подбор кредита или лизинга" },
  "/currency-converter": { group: "Сервисы", label: "Конвертер валют" },
  "/partner": { group: "Информация", label: "Информация для рекламодателей" },
  "/useful-information": { group: "Информация", label: "Полезная информация" },
  "/suggest-topic": { group: "Редакция", label: "Предложить тему редакции" },
  "/commenting-rules": { group: "Редакция", label: "Правила комментирования" },
  "/material-using": { group: "Редакция", label: "Правила использования материалов" },
  "/terms-of-use": { group: "Правила и политики", label: "Пользовательское соглашение" },
  "/privacy-policy": { group: "Правила и политики", label: "Политика конфиденциальности" },
  "/cookie-policy": { group: "Правила и политики", label: "Политика использования cookie-файлов" },
  "/submitting-advert": { group: "Правила и политики", label: "Правила подачи объявлений" },
  "/credit-policy": { group: "Правила и политики", label: "Согласие на обработку персональных данных для фин. организаций" },
  "/promotion": { group: "Разделы", label: "Продвижение" },
  "/pro-subscription": { group: "Разделы", label: "PRO-подписка" },
  "/customs-calculator": { group: "Разделы", label: "Таможенный калькулятор" }
} as const;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("SiteFooter", () => {
  it("exposes all editorial, policy and seller content links", () => {
    act(() => { root.render(createElement(SiteFooter)); });

    const footer = container.querySelector("footer.site-footer");
    expect(footer).not.toBeNull();

    for (const [href, expected] of Object.entries(requiredContentLinks)) {
      const link = footer!.querySelector<HTMLAnchorElement>(`a[href="${href}"]`);
      expect(link?.textContent).toBe(expected.label);
      expect(link?.closest(".footer-group")?.querySelector(".footer-group-title")?.textContent).toBe(expected.group);
    }
    expect(Object.keys(requiredContentLinks)).toHaveLength(19);
  });

  it("keeps the pilot navigation and closed-pilot notice", () => {
    act(() => { root.render(createElement(SiteFooter)); });

    expect(container.querySelector('a[href="/"]')?.textContent).toContain("Авторынок");
    expect(container.querySelector('a[href="/help"]')).not.toBeNull();
    expect(container.querySelector('a[href="/dealers"]')).not.toBeNull();
    expect(container.querySelector('a[href="/sell"]')).not.toBeNull();
    expect(container.querySelector<HTMLAnchorElement>('a[href="/cars?fuel=electric"]')?.textContent).toBe("Электромобили");
    expect(container.querySelector(".footer-note")?.textContent).toContain("Закрытый пилот");
  });
});
