import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SellForm, payloadFor } from "@/components/sell-form";
import { ApiClientError, api } from "@/lib/api";
import { catalogRequestsApi, type CatalogRequest } from "@/lib/catalog-requests";
import type { CatalogItem, CatalogModification, Listing } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

let container: HTMLDivElement;
let root: Root;
let originalValidationPolicyDescriptor: PropertyDescriptor | undefined;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  originalValidationPolicyDescriptor = Object.getOwnPropertyDescriptor(api, "listingValidationPolicy");
  stubListingValidationPolicy(defaultValidationPolicy);
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  if (originalValidationPolicyDescriptor) Object.defineProperty(api, "listingValidationPolicy", originalValidationPolicyDescriptor);
  else Reflect.deleteProperty(api, "listingValidationPolicy");
  vi.restoreAllMocks();
});

function selectValue(label: string, value: string) {
  const select = container.querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`) || [...container.querySelectorAll("label")]
    .find((item) => item.querySelector("span")?.textContent?.trim().startsWith(label))?.querySelector("select");
  if (!select) throw new Error(`Missing select: ${label}`);
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function inputValue(label: string, value: string) {
  const input = container.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`) || [...container.querySelectorAll("label")]
    .find((item) => item.querySelector("span")?.textContent?.trim().startsWith(label))?.querySelector("input");
  if (!input) throw new Error(`Missing input: ${label}`);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function selectedValue(label: string) {
  return [...container.querySelectorAll("label")]
    .find((item) => item.querySelector("span")?.textContent?.trim().startsWith(label))
    ?.querySelector<HTMLSelectElement>("select")?.value;
}

function inputText(label: string) {
  return [...container.querySelectorAll("label")]
    .find((item) => item.querySelector("span")?.textContent?.trim().startsWith(label))
    ?.querySelector<HTMLInputElement>("input")?.value;
}

async function clickContinue() {
  const button = [...container.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.includes("Продолжить"));
  if (!button) throw new Error("Missing continue button");
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}

async function clickStep(step: number) {
  const button = container.querySelector<HTMLButtonElement>(`nav[aria-label="Этапы подачи объявления"] button[aria-label^="Шаг ${step}:"]`);
  if (!button) throw new Error(`Missing form step: ${step}`);
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}

async function clickButton(text: string) {
  const button = [...container.querySelectorAll<HTMLButtonElement>("button")]
    .find((item) => item.textContent?.includes(text));
  if (!button) throw new Error("Missing button: " + text);
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}

function draft(overrides: Partial<Listing> = {}) {
  return {
    id: "draft-1",
    slug: "draft-1",
    title: "",
    status: "draft",
    revision: 1,
    make: { id: "catalog-make", slug: "catalog-make", name: "Каталожная марка" },
    model: { id: "catalog-model", slug: "catalog-model", name: "Каталожная модель" },
    year: 2020,
    mileage_km: 50000,
    fuel: "petrol",
    transmission: "automatic",
    drive: "front",
    price: { amount: "10000", currency: "BYN" as const },
    region: { id: "region-1", slug: "region-1", name: "Область" },
    city: { id: "city-1", slug: "city-1", name: "Город" },
    manual_city: null,
    seller: { type: "private" as const, id: "seller-1", name: "Продавец" },
    created_at: "2026-09-27T00:00:00Z",
    damaged: false,
    parts_only: false,
    description: "Описание",
    condition: "used",
    photo_urls: [],
    ...overrides
  } as Listing;
}

const blankOptionalFields = {
  seller_type: "private",
  make_mode: "catalog",
  model_mode: "catalog",
  make_id: "make-1",
  model_id: "model-1",
  manual_make: "",
  manual_model: "",
  generation_id: "",
  modification_id: "",
  body_type_id: "",
  body_variant_id: "",
  year: "2020",
  mileage_km: "50000",
  fuel: "petrol",
  transmission: "automatic",
  drive: "front",
  engine_volume_l: "",
  power_hp: "",
  condition: "used",
  color: "",
  customs_status: "",
  technical_condition: "",
  body_condition: "",
  exchange: false,
  bargaining: false,
  credit: false,
  leasing: false,
  equipment: [],
  district: "",
  call_hours: "",
  damaged: false,
  parts_only: false,
  vin: "",
  description: "",
  price_amount: "100",
  currency: "BYN",
  region_id: "region-1",
  city_id: "city-1",
  city_mode: "catalog",
  manual_city: "",
  contact_phone: "+375000000000"
} satisfies Parameters<typeof payloadFor>[0];

const catalogGeneration = { id: "generation-1", slug: "generation-1", name: "Поколение 1", model_id: "catalog-model" };

type TestListingValidationPolicy = {
  current_year: number;
  listing_year_min: number;
  new_year_max: number;
  used_year_max: number;
  minimum_photos: { new: number; used: number; damaged: number; parts: number };
  maximum_photos: number;
};

const defaultValidationPolicy: TestListingValidationPolicy = {
  current_year: 2026,
  listing_year_min: 1886,
  new_year_max: 2027,
  used_year_max: 2026,
  minimum_photos: { new: 1, used: 1, damaged: 1, parts: 1 },
  maximum_photos: 30
};

function stubListingValidationPolicy(result: TestListingValidationPolicy | Error | Array<TestListingValidationPolicy | Error>) {
  const method = vi.fn(() => {
    const next = Array.isArray(result) ? result.shift() || new Error("unavailable") : result;
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  Object.defineProperty(api, "listingValidationPolicy", { configurable: true, value: method, writable: true });
  return method;
}

async function renderWithValidationPolicy(
  listing: Listing,
  result: TestListingValidationPolicy | Error | Array<TestListingValidationPolicy | Error> = defaultValidationPolicy
) {
  const policyRequest = stubListingValidationPolicy(result);
  vi.spyOn(api, "listingOptions").mockResolvedValue({
    colors: [], customs_statuses: [], technical_conditions: [], body_conditions: [], equipment: []
  });
  vi.spyOn(api, "catalog").mockResolvedValue({ items: [] });
  vi.spyOn(api, "cities").mockResolvedValue({ items: [listing.city!] });
  vi.spyOn(api, "photos").mockResolvedValue({ items: listing.photos || [] });
  vi.spyOn(api, "listing").mockResolvedValue({ listing });
  vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...listing, revision: listing.revision + 1 } });
  await act(async () => {
    root.render(createElement(SellForm, {
      initialListing: listing,
      makes: [listing.make!], models: [listing.model!], generations: [],
      bodyTypes: [], regions: [listing.region!], cities: [listing.city!], company: null
    }));
    await Promise.resolve();
    await Promise.resolve();
  });
  return policyRequest;
}

describe("listing validation policy", () => {
  it("loads advertised year bounds and lets a new listing use the next year", async () => {
    const policy = { ...defaultValidationPolicy, listing_year_min: 1900 };
    const listing = draft({ contact_phone: "+375291234567" });
    await renderWithValidationPolicy(listing, policy);
    await act(async () => { selectValue("Состояние", "new"); });
    await clickContinue();

    const yearInput = [...container.querySelectorAll("label")]
      .find((item) => item.querySelector("span")?.textContent?.trim() === "Год выпуска")
      ?.querySelector<HTMLInputElement>("input");
    expect(yearInput?.getAttribute("min")).toBe("1900");
    expect(yearInput?.getAttribute("max")).toBe("2027");

    await act(async () => { inputValue("Год выпуска", "2027"); });
    await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Состояние и описание");
    expect(yearInput?.getAttribute("aria-invalid")).toBe(null);
  });

  it("rejects the next year for a used listing using the advertised maximum", async () => {
    const listing = draft({ contact_phone: "+375291234567", condition: "used" });
    await renderWithValidationPolicy(listing);
    await clickContinue();

    const yearInput = [...container.querySelectorAll("label")]
      .find((item) => item.querySelector("span")?.textContent?.trim() === "Год выпуска")
      ?.querySelector<HTMLInputElement>("input");
    expect(yearInput?.getAttribute("max")).toBe("2026");
    await act(async () => { inputValue("Год выпуска", "2027"); });
    await clickContinue();

    expect(container.querySelector("h2")?.textContent).toBe("Автомобиль и характеристики");
    expect(yearInput?.getAttribute("aria-invalid")).toBe("true");
    expect(container.querySelector("#year-error")?.textContent).toContain("2026");
  });

  it("blocks year progression visibly when the policy endpoint fails", async () => {
    const listing = draft({ contact_phone: "+375291234567" });
    await renderWithValidationPolicy(listing, new Error("unavailable"));
    await clickContinue();
    await clickContinue();

    expect(container.querySelector("h2")?.textContent).toBe("Автомобиль и характеристики");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("правила подачи");
  });

  it("retries a failed policy request and resumes the form", async () => {
    const listing = draft({ contact_phone: "+375291234567" });
    const policyRequest = await renderWithValidationPolicy(listing, [new Error("unavailable"), defaultValidationPolicy]);
    await clickContinue();
    await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Автомобиль и характеристики");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Повторить");

    await clickButton("Повторить");
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(policyRequest).toHaveBeenCalledTimes(2);
    await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Состояние и описание");
    expect(container.querySelector("#year-error")).toBe(null);
  });

  it("requires the configured ready-photo minimum and reports it before review", async () => {
    const listing = draft({
      contact_phone: "+375291234567",
      photos: [
        { id: "ready-1", status: "ready", position: 0, is_cover: true },
        { id: "ready-2", status: "ready", position: 1, is_cover: false },
        { id: "processing", status: "processing", position: 2, is_cover: false }
      ]
    });
    const policy = {
      ...defaultValidationPolicy,
      minimum_photos: { ...defaultValidationPolicy.minimum_photos, used: 3 }
    };
    await renderWithValidationPolicy(listing, policy);
    for (let step = 0; step < 4; step += 1) await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.textContent).toContain("Добавьте от 3 до 30 фотографий");
    await clickContinue();

    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.querySelector("#photos-error")?.textContent).toContain("3 обработанные фотографии");
  });

  it.each([
    ["queued", "Дождитесь завершения обработки фотографий."],
    ["processing", "Дождитесь завершения обработки фотографий."],
    ["failed", "Удалите фотографии с ошибкой обработки и загрузите их снова."]
  ] as const)("blocks step 6 while a %s photo remains, even when the ready minimum is met", async (status, message) => {
    const listing = draft({
      contact_phone: "+375291234567",
      photos: [
        { id: "ready", status: "ready", position: 0, is_cover: true },
        { id: status, status, position: 1, is_cover: false }
      ]
    });
    await renderWithValidationPolicy(listing);
    for (let step = 0; step < 4; step += 1) await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");

    await clickContinue();

    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.querySelector("#photos-error")?.textContent).toBe(message);
  });

  it("rechecks refreshed photo states before opening the final review", async () => {
    const readyPhoto = { id: "ready", status: "ready", position: 0, is_cover: true } as const;
    const processingPhoto = { id: "processing", status: "processing", position: 1, is_cover: false } as const;
    const listing = draft({ contact_phone: "+375291234567", photos: [readyPhoto] });
    await renderWithValidationPolicy(listing);
    for (let step = 0; step < 4; step += 1) await clickContinue();
    vi.spyOn(api, "photos").mockResolvedValue({ items: [readyPhoto, processingPhoto] });

    await clickContinue();

    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.querySelector("#photos-error")?.textContent).toBe("Дождитесь завершения обработки фотографий.");
  });

  it("blocks final submission when a failed photo is attached", async () => {
    const listing = draft({
      contact_phone: "+375291234567",
      photos: [
        { id: "ready", status: "ready", position: 0, is_cover: true },
        { id: "failed", status: "failed", position: 1, is_cover: false }
      ]
    });
    await renderWithValidationPolicy(listing);
    for (let step = 0; step < 4; step += 1) await clickContinue();
    const submitListing = vi.spyOn(api, "submitListing").mockResolvedValue({ listing });
    const form = container.querySelector<HTMLFormElement>("form");
    if (!form) throw new Error("Missing listing form");

    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });

    expect(submitListing).not.toHaveBeenCalled();
    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.querySelector("#photos-error")?.textContent).toBe("Удалите фотографии с ошибкой обработки и загрузите их снова.");
  });

  it("refreshes photo states and blocks submission when a photo failed after review opened", async () => {
    const readyPhoto = { id: "ready", status: "ready", position: 0, is_cover: true } as const;
    const failedPhoto = { id: "failed", status: "failed", position: 1, is_cover: false } as const;
    const listing = draft({ contact_phone: "+375291234567", photos: [readyPhoto] });
    await renderWithValidationPolicy(listing);
    for (let step = 0; step < 5; step += 1) await clickContinue();
    expect(container.querySelector("h2")?.textContent).toBe("Проверьте объявление");
    vi.spyOn(api, "photos").mockResolvedValue({ items: [readyPhoto, failedPhoto] });
    const submitListing = vi.spyOn(api, "submitListing").mockResolvedValue({ listing });
    const form = container.querySelector<HTMLFormElement>("form");
    if (!form) throw new Error("Missing listing form");

    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });

    expect(submitListing).not.toHaveBeenCalled();
    expect(container.querySelector("h2")?.textContent).toBe("Фотографии");
    expect(container.querySelector("#photos-error")?.textContent).toBe("Удалите фотографии с ошибкой обработки и загрузите их снова.");
  });
});

async function renderWithModifications(modifications: CatalogModification[], listingOverrides: Partial<Listing> = {}) {
  const listing = draft({ generation: catalogGeneration, ...listingOverrides });
  const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...listing, revision: 2 } });
  vi.spyOn(api, "catalog").mockImplementation(async (kind) => ({ items: kind === "modifications" ? modifications : [] }));
  await act(async () => {
    root.render(createElement(SellForm, {
      initialListing: listing,
      makes: [listing.make!], models: [listing.model!], generations: [catalogGeneration],
      bodyTypes: [], regions: [], cities: [], company: null
    }));
    await Promise.resolve();
  });
  await clickContinue();
  return { listing, updateDraft };
}

describe("draft form payload", () => {
  it("sends null for cleared nullable inputs and an empty string for cleared description", () => {
    expect(payloadFor(blankOptionalFields)).toMatchObject({
      generation_id: null,
      body_type_id: null,
      body_variant_id: null,
      engine_volume_l: null,
      power_hp: null,
      vin: null,
      manual_make: null,
      manual_model: null,
      description: ""
    });
  });

  it("preserves entered nullable values", () => {
    expect(payloadFor({
      ...blankOptionalFields,
      generation_id: "generation-1",
      body_type_id: "body-1",
      body_variant_id: "body-variant-1",
      engine_volume_l: "2.0",
      power_hp: "150",
      vin: "1hgcm82633a004352"
    })).toMatchObject({
      generation_id: "generation-1",
      body_type_id: "body-1",
      body_variant_id: "body-variant-1",
      engine_volume_l: "2.0",
      power_hp: 150,
      vin: "1HGCM82633A004352"
    });
  });

  it("sends every optional listing field using backend enum codes and booleans", () => {
    expect(payloadFor({
      ...blankOptionalFields,
      color: "blue", customs_status: "cleared_rb", technical_condition: "good", body_condition: "minor_damage",
      exchange: true, bargaining: true, credit: true, leasing: false, equipment: ["abs", "rear_camera"],
      district: "Центральный", call_hours: "9:00–20:00"
    })).toMatchObject({
      color: "blue", customs_status: "cleared_rb", technical_condition: "good", body_condition: "minor_damage",
      exchange: true, bargaining: true, credit: true, leasing: false, equipment: ["abs", "rear_camera"],
      district: "Центральный", call_hours: "9:00–20:00"
    });
  });

  it("serializes manually entered make and model as names without catalog IDs", () => {
    const payload = payloadFor({
      ...blankOptionalFields,
      make_mode: "manual",
      model_mode: "manual",
      manual_make: "  Новая марка  ",
      manual_model: "  Новая модель  "
    });

    expect(payload).toMatchObject({ manual_make: "Новая марка", manual_model: "Новая модель" });
    expect(payload).toHaveProperty("make_id", null);
    expect(payload).toHaveProperty("model_id", null);
  });

  it("supports a catalog make with a manually entered model", () => {
    const payload = payloadFor({
      ...blankOptionalFields,
      model_mode: "manual",
      model_id: "",
      manual_model: "Новая модель"
    });

    expect(payload).toMatchObject({ make_id: "make-1", manual_model: "Новая модель" });
    expect(payload).toHaveProperty("manual_make", null);
    expect(payload).toHaveProperty("model_id", null);
  });

  it("sends a trimmed manual city and clears the catalog city ID", () => {
    const payload = payloadFor({
      ...blankOptionalFields,
      city_mode: "manual",
      city_id: "old-city-id",
      manual_city: "  Новый город  "
    });

    expect(payload).toMatchObject({ region_id: "region-1", city_id: null, manual_city: "Новый город" });
  });

  it("keeps catalog city and clears a previous manual city", () => {
    expect(payloadFor(blankOptionalFields)).toMatchObject({
      region_id: "region-1",
      city_id: "city-1",
      manual_city: null
    });
  });
});

describe("manual vehicle entry", () => {
  it("shows only whitelisted API field errors next to their controls", async () => {
    const listing = draft();
    const updateDraft = vi.spyOn(api, "updateDraft").mockRejectedValue(new ApiClientError(422, {
      code: "validation_error",
      message: "Listing is incomplete",
      field_errors: { year: "Year is outside the allowed range", unknown: "do not expose this" }
    }));

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing,
        makes: [listing.make!], models: [listing.model!], generations: [], bodyTypes: [], regions: [listing.region!], cities: [listing.city!], company: null
      }));
    });
    await clickContinue();
    await act(async () => { inputValue("Год выпуска", "2021"); });
    await clickContinue();

    const yearInput = [...container.querySelectorAll("label")]
      .find((item) => item.querySelector("span")?.textContent?.trim() === "Год выпуска")
      ?.querySelector<HTMLInputElement>("input");
    expect(updateDraft).toHaveBeenCalledOnce();
    expect(yearInput?.getAttribute("aria-invalid")).toBe("true");
    expect(yearInput?.getAttribute("aria-describedby")).toBe("year-error");
    expect(container.querySelector("#year-error")?.textContent).toBe("Year is outside the allowed range");
    expect(container.textContent).not.toContain("do not expose this");
  });

  it("ignores a model response for the previously selected make", async () => {
    let resolveMakeA!: (value: { items: { id: string; slug: string; name: string }[] }) => void;
    let resolveMakeB!: (value: { items: { id: string; slug: string; name: string }[] }) => void;
    const makeARequest = new Promise<{ items: { id: string; slug: string; name: string }[] }>((resolve) => { resolveMakeA = resolve; });
    const makeBRequest = new Promise<{ items: { id: string; slug: string; name: string }[] }>((resolve) => { resolveMakeB = resolve; });
    vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "models" && params.make_id === "make-a") return makeARequest;
      if (kind === "models" && params.make_id === "make-b") return makeBRequest;
      return { items: [] };
    });
    const makeAListing = draft({
      make: { id: "make-a", slug: "make-a", name: "Марка A" },
      model: { id: "model-a", slug: "model-a", name: "Модель A" }
    });
    const makeA = { id: "make-a", slug: "make-a", name: "Марка A" };
    const makeB = { id: "make-b", slug: "make-b", name: "Марка B" };
    const modelA = { id: "model-a", slug: "model-a", name: "Модель A" };
    const modelB = { id: "model-b", slug: "model-b", name: "Модель B" };

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: makeAListing,
        makes: [makeA, makeB], models: [modelA], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();
    await act(async () => { selectValue("Марка", "make-b"); });
    await act(async () => { resolveMakeB({ items: [modelB] }); await Promise.resolve(); });
    await act(async () => { resolveMakeA({ items: [modelA] }); await Promise.resolve(); });

    const modelSelect = [...container.querySelectorAll("label")]
      .find((item) => item.querySelector("span")?.textContent?.trim() === "Модель")
      ?.querySelector<HTMLSelectElement>("select");
    expect(modelSelect?.querySelector('option[value="model-b"]')).not.toBeNull();
    expect(modelSelect?.querySelector('option[value="model-a"]')).toBeNull();
  });

  it("exposes all six named form steps and marks the current step", async () => {
    const createDraft = vi.spyOn(api, "createDraft").mockResolvedValue({ listing: draft() });
    await act(async () => {
      root.render(createElement(SellForm, {
        makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });

    const navigation = container.querySelector<HTMLElement>('nav[aria-label="Этапы подачи объявления"]');
    const buttons = [...(navigation?.querySelectorAll<HTMLButtonElement>("button") || [])];
    expect(buttons).toHaveLength(6);
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "Шаг 1: Продавец и предложение",
      "Шаг 2: Автомобиль и характеристики",
      "Шаг 3: Состояние и описание",
      "Шаг 4: Цена, расположение и контакт",
      "Шаг 5: Фотографии",
      "Шаг 6: Проверьте объявление"
    ]);
    expect(buttons[0].getAttribute("aria-current")).toBe("step");
    expect(buttons[1].disabled).toBe(true);
    await clickContinue();
    expect(container.querySelector('nav[aria-label="Этапы подачи объявления"] button[aria-current="step"]')?.getAttribute("aria-label")).toBe("Шаг 2: Автомобиль и характеристики");
    expect(document.activeElement).toBe(container.querySelector("h2"));
    expect(container.querySelector('[role="status"][aria-live="polite"]')?.textContent).toBe("Шаг 2 из 6");
    expect(createDraft).toHaveBeenCalledOnce();
  });

  it("allows revisiting reached steps and keeps future steps locked", async () => {
    await renderWithValidationPolicy(draft({ contact_phone: "+375291234567" }));
    await clickContinue();
    await clickContinue();

    const buttonFor = (step: number) => container.querySelector<HTMLButtonElement>(`nav[aria-label="Этапы подачи объявления"] button[aria-label^="Шаг ${step}:"]`);
    expect(container.querySelector('nav[aria-label="Этапы подачи объявления"] button[aria-current="step"]')?.getAttribute("aria-label")).toBe("Шаг 3: Состояние и описание");
    expect(buttonFor(3)?.disabled).toBe(false);
    expect(buttonFor(4)?.disabled).toBe(true);

    await clickStep(1);
    expect(container.querySelector('nav[aria-label="Этапы подачи объявления"] button[aria-current="step"]')?.getAttribute("aria-label")).toBe("Шаг 1: Продавец и предложение");
    expect(buttonFor(3)?.disabled).toBe(false);
    await clickStep(3);
    expect(container.querySelector("h2")?.textContent).toBe("Состояние и описание");
    expect(buttonFor(4)?.disabled).toBe(true);
  });

  it("rejects non-integer and out-of-range mileage at the field before saving", async () => {
    const created = draft();
    const createDraft = vi.spyOn(api, "createDraft").mockResolvedValue({ listing: created });
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...created, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();

    await act(async () => {
      selectValue("Источник марки", "manual");
      inputValue("Марка вручную", "Редкая марка");
      inputValue("Модель вручную", "Редкая модель");
      inputValue("Год выпуска", "2018");
      inputValue("Пробег, км", "100.5");
      selectValue("Топливо", "diesel");
      selectValue("Коробка передач", "manual");
      selectValue("Привод", "rear");
    });

    const mileageLabel = [...container.querySelectorAll("label")].find((item) => item.querySelector("span")?.textContent?.trim() === "Пробег, км");
    const mileageInput = mileageLabel?.querySelector<HTMLInputElement>("input");
    expect(mileageInput?.min).toBe("0");
    expect(mileageInput?.max).toBe("5000000");
    expect(mileageInput?.step).toBe("1");

    await clickContinue();
    expect(updateDraft).not.toHaveBeenCalled();
    expect(mileageInput?.getAttribute("aria-invalid")).toBe("true");
    expect(mileageInput?.getAttribute("aria-describedby")).toBe("mileage-error");
    expect(container.querySelector("#mileage-error")?.textContent).toBe("Укажите целое число от 0 до 5 000 000 км.");
    expect(document.activeElement).toBe(mileageInput);

    await act(async () => { inputValue("Пробег, км", "5000001"); });
    await clickContinue();
    expect(updateDraft).not.toHaveBeenCalled();
    expect(container.querySelector("#mileage-error")?.textContent).toBe("Укажите целое число от 0 до 5 000 000 км.");
    expect(document.activeElement).toBe(mileageInput);

    await act(async () => { inputValue("Пробег, км", "0"); });
    await clickContinue();
    expect(updateDraft).toHaveBeenCalledOnce();
    expect(container.querySelector('nav[aria-label="Этапы подачи объявления"] button[aria-current="step"]')?.getAttribute("aria-label")).toBe("Шаг 3: Состояние и описание");
    expect(createDraft).toHaveBeenCalledOnce();
  });

  it("lets a seller enter a vehicle absent from the catalog and saves only manual names", async () => {
    const created = draft();
    const createDraft = vi.spyOn(api, "createDraft").mockResolvedValue({ listing: created });
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...created, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        makes: [{ id: "catalog-make", slug: "catalog-make", name: "Каталожная марка" }],
        models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();

    await act(async () => {
      selectValue("Источник марки", "manual");
      inputValue("Марка вручную", "Редкая марка");
      inputValue("Модель вручную", "Редкая модель");
      inputValue("Год выпуска", "2018");
      inputValue("Пробег, км", "80000");
      selectValue("Топливо", "diesel");
      selectValue("Коробка передач", "manual");
      selectValue("Привод", "rear");
    });
    await clickContinue();

    expect(createDraft).toHaveBeenCalledTimes(1);
    expect(updateDraft).toHaveBeenCalledTimes(1);
    const payload = updateDraft.mock.calls[0][2];
    expect(payload).toMatchObject({ manual_make: "Редкая марка", manual_model: "Редкая модель" });
    expect(payload).toHaveProperty("make_id", null);
    expect(payload).toHaveProperty("model_id", null);
  });

  it("reopens an existing manually cataloged listing without treating fallback IDs as catalog IDs", async () => {
    const manualListing = draft({
      make: { id: "00000000-0000-0000-0000-000000000000", slug: "manual-make-hash", name: "Ручная марка" },
      model: { id: "00000000-0000-0000-0000-000000000000", slug: "manual-model-hash", name: "Ручная модель" }
    });
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...manualListing, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: manualListing,
        makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();
    expect(container.querySelector<HTMLSelectElement>('select[aria-label="Источник марки"]')?.value).toBe("manual");
    expect(container.querySelector<HTMLInputElement>('input[aria-label="Марка вручную"]')?.value).toBe("Ручная марка");
    expect(container.querySelector<HTMLInputElement>('input[aria-label="Модель вручную"]')?.value).toBe("Ручная модель");

    await act(async () => { inputValue("Модель вручную", "Изменённая модель"); });
    await clickContinue();

    const payload = updateDraft.mock.calls[0][2];
    expect(payload).toMatchObject({ manual_make: "Ручная марка", manual_model: "Изменённая модель" });
    expect(payload).toHaveProperty("make_id", null);
    expect(payload).toHaveProperty("model_id", null);
  });

  it("reopens an incomplete draft with nullable catalog and price fields", async () => {
    const partialListing = draft({
      title: "",
      make: null,
      model: null,
      generation: null,
      year: null,
      mileage_km: null,
      fuel: null,
      transmission: null,
      drive: null,
      price: null,
      region: null,
      city: null,
      condition: null
    });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: partialListing,
        makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();

    expect(container.querySelector<HTMLSelectElement>('select[aria-label="Источник марки"]')?.value).toBe("catalog");
    expect(selectedValue("Марка")).toBe("");
    expect(inputText("Год выпуска")).toBe("");
    expect(inputText("Пробег, км")).toBe("");
  });
});

describe("catalog modifications", () => {
  it("lets a seller save manual parameters and submit a missing-modification review request", async () => {
    const listing = draft({ generation: catalogGeneration });
    const expectedRequest = {
      id: "catalog-request-1",
      listing_id: listing.id,
      listing_revision: listing.revision,
      status: "pending",
      revision: 1,
      snapshot: { catalog: {}, manual_identity: {}, manual_parameters: {} },
      manual_modification_name: "2.0 TDI quattro",
      note: "Код двигателя указан на табличке.",
      resolved_modification: null,
      review_reason: null,
      created_at: "2026-10-01T00:00:00Z",
      reviewed_at: null
    } as CatalogRequest;
    vi.spyOn(catalogRequestsApi, "listForListing").mockResolvedValue({ items: [] });
    const createRequest = vi.spyOn(catalogRequestsApi, "createForListing")
      .mockResolvedValue({ request: expectedRequest });
    const { updateDraft } = await renderWithModifications([], {
      generation: catalogGeneration,
      engine_volume_l: "2.0",
      power_hp: 150
    });

    await act(async () => { selectValue("Модификация", "__missing_modification__"); });
    expect(container.textContent).toContain("Не нашёл модификацию");
    expect(container.querySelector('input[aria-label="Название модификации"]')).not.toBeNull();
    expect(container.querySelector('textarea[aria-label="Комментарий для каталога"]')).not.toBeNull();
    inputValue("Название модификации", "2.0 TDI quattro");
    inputValue("Объём двигателя, л", "2.2");
    const note = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Комментарий для каталога"]');
    if (!note) throw new Error("Missing catalog request note field");
    const noteSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    noteSetter?.call(note, "Код двигателя указан на табличке.");
    note.dispatchEvent(new Event("input", { bubbles: true }));
    await clickButton("Отправить на проверку справочника");

    expect(updateDraft).toHaveBeenCalled();
    expect(createRequest).toHaveBeenCalledWith(
      listing.id,
      {
        expected_listing_revision: listing.revision + 1,
        manual_modification_name: "2.0 TDI quattro",
        note: "Код двигателя указан на табличке."
      },
      expect.any(String)
    );
    expect(container.textContent).toContain("Запрос отправлен в справочник");
  });

  it("retries a failed catalog request with the same idempotency key and shows its queue status", async () => {
    const listing = draft({ generation: catalogGeneration });
    const pendingRequest = {
      id: "catalog-request-retry",
      listing_id: listing.id,
      listing_revision: listing.revision + 1,
      status: "pending",
      revision: 1,
      snapshot: { catalog: {}, manual_identity: {}, manual_parameters: {} },
      manual_modification_name: "Редкая версия",
      note: null,
      resolved_modification: null,
      review_reason: null,
      created_at: "2026-10-01T00:00:00Z",
      reviewed_at: null
    } as CatalogRequest;
    vi.spyOn(catalogRequestsApi, "listForListing").mockResolvedValue({ items: [] });
    const createRequest = vi.spyOn(catalogRequestsApi, "createForListing")
      .mockRejectedValueOnce(new Error("Network unavailable"))
      .mockResolvedValueOnce({ request: pendingRequest });
    await renderWithModifications([], { generation: catalogGeneration });
    await act(async () => { selectValue("Модификация", "__missing_modification__"); });
    inputValue("Название модификации", "Редкая версия");

    await clickButton("Отправить на проверку справочника");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("повторите попытку");
    await clickButton("Повторить отправку");

    expect(createRequest).toHaveBeenCalledTimes(2);
    expect(createRequest.mock.calls[0][2]).toBe(createRequest.mock.calls[1][2]);
    expect(container.textContent).toContain("Ожидает проверки");
  });

  it("shows Drom data and maps known Russian specifications to the form values", async () => {
    const modification: CatalogModification = {
      id: "mod-drom-1", slug: "drom-1", name: "2.2 AT Turbo",
      source: { name: "Drom", id: "268729", url: "https://www.drom.ru/catalog/audi/200/268729/" },
      specs: {
        engine_code: "MC", frame_code: "443-44Q", engine_l: 2.2, power_hp: 165,
        fuel: "бензин", transmission: "АКПП", drive: "передний привод",
        production_period_raw: "02.1988 - 07.1991", summary_raw: null
      }
    };
    const { updateDraft } = await renderWithModifications([modification]);

    await act(async () => { selectValue("Модификация", modification.id); });
    expect(container.textContent).toContain("Источник: Drom · ID 268729");
    expect(container.textContent).toContain("Код двигателяMC");
    expect(container.textContent).toContain("Код рамы443-44Q");
    expect(container.textContent).toContain("02.1988 - 07.1991");
    expect(selectedValue("Топливо")).toBe("petrol");
    expect(selectedValue("Коробка передач")).toBe("automatic");
    expect(selectedValue("Привод")).toBe("front");
    expect(inputText("Объём двигателя, л")).toBe("2.2");
    expect(inputText("Мощность, л.с.")).toBe("165");

    await clickContinue();
    expect(updateDraft.mock.calls[0]?.[2]).toMatchObject({
      modification_id: modification.id,
      engine_volume_l: "2.2",
      power_hp: 165,
      fuel: "petrol",
      transmission: "automatic",
      drive: "front"
    });
  });

  it("maps Drom dual-fuel, CVT, four-wheel-drive, and rear-engine labels without hiding their raw values", async () => {
    const modification: CatalogModification = {
      id: "mod-drom-special", slug: "drom-special", name: "Специальная версия",
      source: { name: "Drom", id: "special-1", url: "https://www.drom.ru/catalog/example/special/" },
      specs: {
        engine_code: null, frame_code: null, engine_l: null, power_hp: null,
        fuel: "газ/бензин", transmission: "вариатор (CVT)", drive: "полный привод (4WD)",
        production_period_raw: null, summary_raw: null
      }
    };
    const rearEngineModification: CatalogModification = {
      ...modification,
      id: "mod-drom-rear-engine", slug: "drom-rear-engine", name: "Заднемоторная версия",
      specs: { ...modification.specs!, drive: "задний привод, двигатель посередине" }
    };
    const rearPositionModification: CatalogModification = {
      ...rearEngineModification,
      id: "mod-drom-rear-position", slug: "drom-rear-position", name: "Версия с двигателем сзади",
      specs: { ...modification.specs!, drive: "задний привод, заднее расположение двигателя" }
    };
    await renderWithModifications([modification, rearEngineModification, rearPositionModification]);

    await act(async () => { selectValue("Модификация", modification.id); });
    expect(selectedValue("Топливо")).toBe("lpg");
    expect(selectedValue("Коробка передач")).toBe("cvt");
    expect(selectedValue("Привод")).toBe("all");
    expect(container.textContent).toContain("газ/бензин");
    expect(container.textContent).toContain("вариатор (CVT)");
    expect(container.textContent).toContain("полный привод (4WD)");

    await act(async () => { selectValue("Модификация", rearEngineModification.id); });
    expect(selectedValue("Привод")).toBe("rear");
    expect(container.textContent).toContain("задний привод, двигатель посередине");

    await act(async () => { selectValue("Модификация", rearPositionModification.id); });
    expect(selectedValue("Привод")).toBe("rear");
    expect(container.textContent).toContain("задний привод, заднее расположение двигателя");
  });

  it("keeps seller values when Drom fields are absent or have an unknown value", async () => {
    const modification: CatalogModification = {
      id: "mod-drom-unknown", slug: "drom-unknown", name: "Редкая версия",
      source: { name: "Drom", id: "unknown-1", url: "https://www.drom.ru/catalog/example/" },
      specs: {
        engine_code: null, frame_code: null, engine_l: null, power_hp: null,
        fuel: "неизвестное топливо", transmission: "МКПП", drive: "неизвестный привод",
        production_period_raw: null, summary_raw: "Сырое описание комплектации"
      }
    };
    await renderWithModifications([modification], {
      fuel: "hybrid", transmission: "automatic", drive: "rear", engine_volume_l: "2.4", power_hp: 180
    });

    await act(async () => { selectValue("Модификация", modification.id); });
    expect(container.textContent).toContain("Сырое описание комплектации");
    expect(selectedValue("Топливо")).toBe("hybrid");
    expect(selectedValue("Коробка передач")).toBe("manual");
    expect(selectedValue("Привод")).toBe("rear");
    expect(inputText("Объём двигателя, л")).toBe("2.4");
    expect(inputText("Мощность, л.с.")).toBe("180");
  });

  it("retains summary-only Drom rows and handles a missing-summary row without fabricated values", async () => {
    const summaryOnly: CatalogModification = {
      id: "mod-summary", slug: "summary-only", name: "Комплектация с описанием",
      source: { name: "Drom", id: "summary-1", url: "https://www.drom.ru/catalog/example/summary/" },
      specs: {
        engine_code: null, frame_code: null, engine_l: null, power_hp: null,
        fuel: null, transmission: null, drive: null,
        production_period_raw: "2010 - 2012", summary_raw: "2.0 л, бензин, автомат"
      }
    };
    const missingSummary: CatalogModification = {
      id: "mod-empty", slug: "empty", name: "Версия без описания",
      source: { name: "Drom", id: "empty-1", url: "https://www.drom.ru/catalog/example/empty/" },
      specs: {
        engine_code: null, frame_code: null, engine_l: null, power_hp: null,
        fuel: null, transmission: null, drive: null,
        production_period_raw: null, summary_raw: null
      }
    };
    await renderWithModifications([summaryOnly, missingSummary], {
      fuel: "diesel", transmission: "manual", drive: "all", engine_volume_l: "1.6", power_hp: 105
    });

    await act(async () => { selectValue("Модификация", summaryOnly.id); });
    expect(container.textContent).toContain("2010 - 2012");
    expect(container.textContent).toContain("2.0 л, бензин, автомат");
    expect(selectedValue("Топливо")).toBe("diesel");
    expect(inputText("Объём двигателя, л")).toBe("1.6");

    await act(async () => { selectValue("Модификация", missingSummary.id); });
    expect(container.textContent).toContain("Для этой модификации характеристики в каталоге не указаны.");
    expect(container.textContent).not.toContain("Описание комплектации:");
    expect(selectedValue("Топливо")).toBe("diesel");
    expect(inputText("Объём двигателя, л")).toBe("1.6");
  });

  it("allows a non-Drom modification without applying catalog values to seller fields", async () => {
    const modification: CatalogModification = { id: "mod-local", slug: "local", name: "Локальная версия" };
    const { updateDraft } = await renderWithModifications([modification], {
      fuel: "diesel", transmission: "manual", drive: "rear", engine_volume_l: "1.9", power_hp: 125
    });

    await act(async () => { selectValue("Модификация", modification.id); });
    expect(container.textContent).toContain("Для этой модификации характеристики в каталоге не указаны.");
    expect(selectedValue("Топливо")).toBe("diesel");
    expect(selectedValue("Коробка передач")).toBe("manual");
    expect(inputText("Объём двигателя, л")).toBe("1.9");

    await clickContinue();
    expect(updateDraft.mock.calls[0]?.[2]).toMatchObject({
      modification_id: modification.id,
      fuel: "diesel",
      transmission: "manual",
      drive: "rear",
      engine_volume_l: "1.9",
      power_hp: 125
    });
  });
});

describe("generation-specific body variants", () => {
  it("restores the saved variant and saves a newly selected variant", async () => {
    const savedVariant: CatalogItem = { id: "body-variant-1", slug: "sedan", name: "Седан", generation_id: catalogGeneration.id };
    const selectedVariant: CatalogItem = { id: "body-variant-2", slug: "wagon", name: "Универсал", generation_id: catalogGeneration.id };
    const listing = draft({
      generation: catalogGeneration,
      body_variant_id: savedVariant.id,
      body_variant: savedVariant
    });
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind) => ({
      items: kind === "body-variants" ? [savedVariant, selectedVariant] : []
    }));
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...listing, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing,
        makes: [listing.make!], models: [listing.model!], generations: [catalogGeneration],
        bodyTypes: [], regions: [], cities: [], company: null
      }));
      await Promise.resolve();
    });
    await clickContinue();

    expect(catalog).toHaveBeenCalledWith("body-variants", { generation_id: catalogGeneration.id });
    expect(selectedValue("Вариант кузова")).toBe(savedVariant.id);
    expect(container.textContent).toContain("Седан");

    await act(async () => { selectValue("Вариант кузова", selectedVariant.id); });
    await clickContinue();

    expect(updateDraft.mock.calls[0]?.[2]).toMatchObject({ body_variant_id: selectedVariant.id });
  });

  it("shows the selected body variant in the final listing review", async () => {
    const bodyVariant: CatalogItem = { id: "body-variant-review", slug: "sedan", name: "Седан", generation_id: catalogGeneration.id };
    const readyPhoto = { id: "photo-ready", status: "ready", position: 0, is_cover: true } as const;
    const listing = draft({
      contact_phone: "+375000000000",
      generation: catalogGeneration,
      body_variant_id: bodyVariant.id,
      body_variant: bodyVariant,
      photos: [readyPhoto]
    });
    vi.spyOn(api, "catalog").mockImplementation(async (kind) => ({ items: kind === "body-variants" ? [bodyVariant] : [] }));
    vi.spyOn(api, "cities").mockResolvedValue({ items: [listing.city!] });
    vi.spyOn(api, "photos").mockResolvedValue({ items: [readyPhoto] });
    vi.spyOn(api, "listing").mockResolvedValue({ listing });
    vi.spyOn(api, "updateDraft").mockResolvedValue({ listing });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing,
        makes: [listing.make!], models: [listing.model!], generations: [catalogGeneration],
        bodyTypes: [], regions: [listing.region!], cities: [listing.city!], company: null
      }));
      await Promise.resolve();
    });
    for (let step = 0; step < 5; step += 1) await clickContinue();

    const variantRow = [...container.querySelectorAll<HTMLElement>(".review-list > div")]
      .find((row) => row.querySelector("dt")?.textContent === "Вариант кузова");
    expect(variantRow?.querySelector("dd")?.textContent).toBe("Седан");
  });

  it("shows the saved seller details and processed photos in the final review", async () => {
    const coverPhoto = { id: "photo-cover", url: "/uploads/cover.webp", status: "ready", position: 0, is_cover: true } as const;
    const secondPhoto = { id: "photo-side", url: "/uploads/side.webp", status: "ready", position: 1, is_cover: false } as const;
    const listing = draft({
      description: "Осмотрен и обслужен.\nБез вложений.",
      engine_volume_l: "2.0",
      power_hp: 150,
      contact_phone: "+375291234567",
      seller: { type: "company", id: "seller-1", name: "Автосалон" },
      photos: [coverPhoto, secondPhoto]
    });
    vi.spyOn(api, "catalog").mockResolvedValue({ items: [] });
    vi.spyOn(api, "cities").mockResolvedValue({ items: [listing.city!] });
    vi.spyOn(api, "photos").mockResolvedValue({ items: [coverPhoto, secondPhoto] });
    vi.spyOn(api, "listing").mockResolvedValue({ listing });
    vi.spyOn(api, "updateDraft").mockResolvedValue({ listing });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing,
        makes: [listing.make!], models: [listing.model!], generations: [],
        bodyTypes: [], regions: [listing.region!], cities: [listing.city!],
        company: { id: "seller-1", slug: "dealer", name: "Автосалон", unp: "123456789", address: "Минск", phone: "+375291234567", business_hours: null, status: "approved", revision: 1, moderation_reason: null }
      }));
    });
    for (let step = 0; step < 5; step += 1) await clickContinue();

    const valueFor = (label: string) => [...container.querySelectorAll<HTMLElement>(".review-list > div")]
      .find((row) => row.querySelector("dt")?.textContent === label)
      ?.querySelector("dd")?.textContent;
    expect(valueFor("Описание")).toBe("Осмотрен и обслужен.\nБез вложений.");
    expect(valueFor("Топливо")).toBe("Бензин");
    expect(valueFor("Коробка передач")).toBe("Автомат");
    expect(valueFor("Привод")).toBe("Передний");
    expect(valueFor("Объём двигателя и мощность")).toBe("2.0 л · 150 л.с.");
    expect(valueFor("Тип продавца")).toBe("Компания");
    expect(valueFor("Телефон для связи")).toBe("+375291234567");
    expect(valueFor("Фотографии")).toBe("2 обработано");

    const thumbnails = [...container.querySelectorAll<HTMLImageElement>(".review-photo-list img")];
    expect(thumbnails).toHaveLength(2);
    expect(thumbnails.map((image) => [image.getAttribute("src"), image.alt])).toEqual([
      ["/uploads/cover.webp", "Обложка объявления"],
      ["/uploads/side.webp", "Фотография 2"]
    ]);
  });

  it("clears variant and modification on generation change and ignores stale variant results", async () => {
    const secondGeneration: CatalogItem = { id: "generation-2", slug: "generation-2", name: "Поколение 2", model_id: "catalog-model" };
    const firstVariant: CatalogItem = { id: "variant-generation-1", slug: "sedan", name: "Седан", generation_id: catalogGeneration.id };
    const secondVariant: CatalogItem = { id: "variant-generation-2", slug: "coupe", name: "Купе", generation_id: secondGeneration.id };
    const firstModification: CatalogModification = { id: "modification-generation-1", slug: "first", name: "Модификация 1" };
    let resolveFirstVariants!: (result: { items: CatalogItem[] }) => void;
    const firstVariants = new Promise<{ items: CatalogItem[] }>((resolve) => { resolveFirstVariants = resolve; });
    vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "models") return { items: [{ id: "catalog-model", slug: "catalog-model", name: "Каталожная модель" }] };
      if (kind === "generations") return { items: [catalogGeneration, secondGeneration] };
      if (kind === "body-variants" && params.generation_id === catalogGeneration.id) return firstVariants;
      if (kind === "body-variants" && params.generation_id === secondGeneration.id) return { items: [secondVariant] };
      if (kind === "modifications" && params.generation_id === catalogGeneration.id) return { items: [firstModification] };
      return { items: [] };
    });
    const listing = draft({
      generation: catalogGeneration,
      body_variant_id: firstVariant.id,
      body_variant: firstVariant,
      modification_id: firstModification.id,
      modification: firstModification
    });
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...listing, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing,
        makes: [listing.make!], models: [listing.model!], generations: [catalogGeneration, secondGeneration],
        bodyTypes: [], regions: [], cities: [], company: null
      }));
    });
    await clickContinue();
    expect(selectedValue("Вариант кузова")).toBe(firstVariant.id);
    expect(selectedValue("Модификация")).toBe(firstModification.id);

    await act(async () => {
      selectValue("Поколение", secondGeneration.id);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(selectedValue("Вариант кузова")).toBe("");
    expect(selectedValue("Модификация")).toBe("");
    expect(container.querySelector('option[value="variant-generation-2"]')).not.toBeNull();

    await act(async () => { resolveFirstVariants({ items: [firstVariant] }); await Promise.resolve(); });
    expect(container.querySelector('option[value="variant-generation-1"]')).toBeNull();
    expect(container.querySelector('option[value="variant-generation-2"]')).not.toBeNull();

    await clickContinue();
    expect(updateDraft.mock.calls[0]?.[2]).toMatchObject({ body_variant_id: null, modification_id: null });
  });
});

describe("manual city entry", () => {
  it("restores and saves a manually entered city while keeping its region", async () => {
    const manualListing = draft({
      city: null,
      manual_city: "Заславль",
      contact_phone: "+375000000000"
    });
    const updateDraft = vi.spyOn(api, "updateDraft").mockResolvedValue({ listing: { ...manualListing, revision: 2 } });

    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: manualListing,
        makes: [], models: [], generations: [], bodyTypes: [],
        regions: [manualListing.region!], cities: [], company: null
      }));
    });
    await clickContinue();
    await clickContinue();
    await clickContinue();

    expect(container.querySelector<HTMLSelectElement>('select[aria-label="Источник населённого пункта"]')?.value).toBe("manual");
    expect(container.querySelector<HTMLInputElement>('input[aria-label="Населённый пункт вручную"]')?.value).toBe("Заславль");
    expect(container.querySelector<HTMLInputElement>('input[aria-label="Населённый пункт вручную"]')?.maxLength).toBe(160);

    await act(async () => { selectValue("Область", ""); });
    expect(container.querySelector<HTMLInputElement>('input[aria-label="Населённый пункт вручную"]')?.disabled).toBe(true);
    await clickContinue();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Выберите область.");

    await act(async () => { selectValue("Область", "region-1"); });
    await act(async () => { inputValue("Населённый пункт вручную", "  Новый Заславль  "); });
    await clickContinue();

    const payload = updateDraft.mock.calls.at(-1)?.[2];
    expect(payload).toMatchObject({ region_id: "region-1", city_id: null, manual_city: "Новый Заславль" });
  });
});
