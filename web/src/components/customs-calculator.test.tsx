import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CustomsCalculator } from "@/components/customs-calculator";
import type { CustomsCalculatorMeta, CustomsCalculationResult } from "@/lib/customs-calculator";

const availableMeta: CustomsCalculatorMeta = {
  scenario: "private_m1_personal_use_outside_eaeu",
  supported_currencies: ["EUR", "USD", "BYN", "RUB", "CNY"],
  supported_engines: ["petrol", "diesel"],
  calculation_available: true,
  unavailable_reason: null,
  rules_version: "customs-2026-v1",
  verified_on: "2026-10-04",
  sources: ["https://customs.gov.by/source-one"],
  scope_notes: ["Физическое лицо: M1, бензиновый или дизельный двигатель, личное пользование, вне ЕАЭС, Беларусь, без льгот."]
};

const unavailableMeta: CustomsCalculatorMeta = {
  ...availableMeta,
  calculation_available: false,
  unavailable_reason: "customs_rules_unverified",
  rules_version: null,
  verified_on: null,
  sources: ["https://customs.gov.by/source-one", "https://customs.gov.by/gtk-control"]
};

const result: CustomsCalculationResult = {
  calculation_date: "2026-10-04",
  rules_version: "customs-2026-v1",
  age_band: "over_3_to_5_years",
  customs_value_eur: "10625.63",
  duty_eur: "4590.00",
  duty_byn: "16065.00",
  recycling_fee_byn: "5.25",
  customs_fee_byn: "1.20",
  total_byn: "16071.45",
  rate_date: "2026-10-04",
  rates_used: [
    { currency: "EUR", official_rate: "3.5", scale: 1, byn_per_unit: "3.5" },
    { currency: "USD", official_rate: "3.2", scale: 1, byn_per_unit: "3.2" }
  ],
  sources: ["https://customs.gov.by/source-one", "https://api.nbrb.by/exrates/rates?ondate=2026-10-04"],
  warnings: ["Предварительная оценка; окончательную таможенную стоимость определяет таможня."]
};

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
  vi.unstubAllGlobals();
});

function responseFor(url: string, calculation = result) {
  if (url.endsWith("/meta")) return Response.json(availableMeta);
  if (url.endsWith("/calculate")) return Response.json(calculation);
  throw new Error(`Unexpected request: ${url}`);
}

async function render(fetchImplementation?: typeof fetch) {
  vi.stubGlobal("fetch", fetchImplementation || vi.fn(async (input: RequestInfo | URL) => responseFor(String(input))));
  await act(async () => {
    root.render(createElement(CustomsCalculator));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function setValue(element: HTMLInputElement | HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function chooseRadio(name: string, value: string) {
  const input = container.querySelector<HTMLInputElement>(`input[name="${name}"][value="${value}"]`)!;
  input.checked = true;
  input.dispatchEvent(new Event("click", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

async function fillForm() {
  await act(async () => {
  setValue(container.querySelector<HTMLInputElement>('input[name="price_amount"]')!, "12500.75");
  setValue(container.querySelector<HTMLSelectElement>('select[name="currency"]')!, "USD");
  setValue(container.querySelector<HTMLInputElement>('input[name="manufacture_date"]')!, "2020-04-12");
  chooseRadio("engine_type", "diesel");
  setValue(container.querySelector<HTMLInputElement>('input[name="engine_volume_cc"]')!, "1998");
  container.querySelector<HTMLInputElement>('input[name="personal_use"]')!.click();
  container.querySelector<HTMLInputElement>('input[name="origin_outside_eaeu"]')!.click();
    await Promise.resolve();
  });
}

async function submitForm() {
  await act(async () => {
    container.querySelector<HTMLFormElement>("form")!.requestSubmit();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("customs calculator form", () => {
  it("shows the server publication gate without offering or inventing result sums", async () => {
    await render(vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/meta")) return Response.json(unavailableMeta);
      throw new Error("The public calculation gate must stop the POST");
    }));

    expect(container.textContent).toContain("контрольные примеры ещё не подтверждены по данным ГТК");
    expect(container.querySelector('a[href="https://customs.gov.by/gtk-control"]')).not.toBeNull();
    expect(container.querySelector('[role="status"]')).not.toBeNull();
    await fillForm();
    await submitForm();
    expect(container.querySelector(".result")).toBeNull();
    expect(container.textContent).not.toContain("16 071,45");
    expect(container.textContent).not.toContain("4590.00 BYN");
  });

  it("sends the exact manually entered payload and renders the server breakdown and provenance", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input: RequestInfo | URL) => responseFor(String(input)));
    await render(fetchMock);
    await fillForm();

    await submitForm();

    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/calculate"))).toHaveLength(1);
    const calculateCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/calculate"))!;
    expect(JSON.parse(String(calculateCall[1]?.body))).toEqual({
      price_amount: "12500.75",
      currency: "USD",
      manufacture_date: "2020-04-12",
      engine_type: "diesel",
      engine_volume_cc: 1998,
      personal_use: true,
      origin_outside_eaeu: true
    });
    expect(container.textContent).toContain("10625.63 EUR");
    expect(container.textContent).toContain("4590.00 EUR");
    expect(container.textContent).toContain("16065.00 BYN");
    expect(container.textContent).toContain("5.25 BYN");
    expect(container.textContent).toContain("1.20 BYN");
    expect(container.textContent).toContain("16071.45 BYN");
    expect(container.textContent).toContain("3.5 BYN за 1 EUR");
    expect(container.textContent).toContain("2026-10-04");
    expect(container.textContent).toContain("Окончательные платежи в BYN рассчитываются по курсу НБРБ на день регистрации пассажирской таможенной декларации.");
    expect(container.textContent).toContain("Предварительная оценка; окончательную таможенную стоимость определяет таможня.");
    expect(container.querySelector('a[href="https://customs.gov.by/source-one"]')?.textContent).toContain("Государственный таможенный комитет Республики Беларусь");
    expect(container.textContent).toContain("дата сверки правил: 2026-10-04");
  });

  it("uses native required validation for an incomplete or invalid date and amount", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => responseFor(String(input)));
    await render(fetchMock);
    const form = container.querySelector<HTMLFormElement>("form")!;
    expect(form.checkValidity()).toBe(false);
    await submitForm();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/calculate"))).toBe(false);

    await fillForm();
    await act(async () => { setValue(container.querySelector<HTMLInputElement>('input[name="price_amount"]')!, "0"); });
    expect(form.checkValidity()).toBe(false);
    await act(async () => { setValue(container.querySelector<HTMLInputElement>('input[name="price_amount"]')!, "12,50"); });
    expect(form.checkValidity()).toBe(false);
    await act(async () => {
      setValue(container.querySelector<HTMLInputElement>('input[name="price_amount"]')!, "12.50");
      setValue(container.querySelector<HTMLInputElement>('input[name="manufacture_date"]')!, "2020-02-30");
    });
    expect(container.querySelector<HTMLInputElement>('input[name="manufacture_date"]')!.value).toBe("");
    expect(form.checkValidity()).toBe(false);
  });

  it("clears a previous result on every edit and ignores a late response from the old values", async () => {
    let resolveOld!: (response: Response) => void;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/meta")) return Promise.resolve(Response.json(availableMeta));
      return new Promise<Response>((resolve) => { resolveOld = resolve; });
    });
    await render(fetchMock as typeof fetch);
    await fillForm();
    const form = container.querySelector<HTMLFormElement>("form")!;
    await act(async () => { form.requestSubmit(); await Promise.resolve(); });
    expect(container.querySelector('[role="status"]')?.textContent).toContain("Выполняем расчёт");

    await act(async () => { setValue(container.querySelector<HTMLInputElement>('input[name="price_amount"]')!, "14000"); });
    expect(container.textContent).not.toContain("16071.45 BYN");
    await act(async () => {
      resolveOld(Response.json(result));
      await Promise.resolve();
    });
    expect(container.textContent).not.toContain("16071.45 BYN");
    expect(container.querySelector('[role="status"]')?.textContent || "").not.toContain("Расчёт готов");
  });

  it("translates API error codes and server field names into Russian retry guidance", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/meta")) return Response.json(availableMeta);
      return Response.json({
        code: "customs_input_invalid",
        message: "English backend error must not be shown",
        field_errors: { manufacture_date: "invalid date", engine_volume_cc: "must be positive" },
        request_id: "request-2"
      }, { status: 422 });
    });
    await render(fetchMock as typeof fetch);
    await fillForm();
    await submitForm();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Проверьте дату выпуска, объём двигателя");
    expect(container.querySelector('[role="alert"]')?.textContent).not.toContain("English backend error");
    expect(container.textContent).toContain("Введите точную дату выпуска");
    expect(container.textContent).toContain("Введите целый объём двигателя от 1 до 100 000 см³");
    expect(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(false);
  });

  it("loads unavailable metadata again when retrying a failed metadata request", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(Response.json(unavailableMeta));
    await render(fetchMock as typeof fetch);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Не удалось загрузить сведения о правилах");

    const retry = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Повторить"));
    await act(async () => { retry?.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).toContain("контрольные примеры ещё не подтверждены по данным ГТК");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
