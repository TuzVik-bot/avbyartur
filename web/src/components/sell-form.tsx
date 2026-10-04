"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, ImagePlus, LoaderCircle, Star, Trash2 } from "lucide-react";
import { api, ApiClientError, type ListingOptions } from "@/lib/api";
import { catalogRequestsApi, type CatalogRequest } from "@/lib/catalog-requests";
import type { CatalogItem, CatalogModification, Company, Listing, ListingDraftInput, ListingPhoto } from "@/lib/types";

const FUEL_OPTIONS = ["petrol", "diesel", "hybrid", "electric", "lpg", "other"] as const satisfies readonly NonNullable<ListingDraftInput["fuel"]>[];
const TRANSMISSION_OPTIONS = ["manual", "automatic", "robot", "cvt", "other"] as const satisfies readonly NonNullable<ListingDraftInput["transmission"]>[];
const DRIVE_OPTIONS = ["front", "rear", "all", "other"] as const satisfies readonly NonNullable<ListingDraftInput["drive"]>[];
const CONDITION_OPTIONS = ["new", "used"] as const satisfies readonly NonNullable<ListingDraftInput["condition"]>[];

type ListingValidationPolicy = Awaited<ReturnType<typeof api.listingValidationPolicy>>;

function minimumPhotoCount(
  policy: ListingValidationPolicy,
  fields: Pick<FormFields, "condition" | "damaged" | "parts_only">
) {
  if (fields.parts_only) return policy.minimum_photos.parts;
  if (fields.damaged) return policy.minimum_photos.damaged;
  return fields.condition === "new" ? policy.minimum_photos.new : policy.minimum_photos.used;
}

function photoCountPhrase(count: number) {
  const lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return "обработанных фотографий";
  const last = count % 10;
  if (last === 1) return "обработанную фотографию";
  if (last >= 2 && last <= 4) return "обработанные фотографии";
  return "обработанных фотографий";
}

function enumValue<T extends readonly string[]>(value: string | null | undefined, options: T): T[number] | "" {
  return options.find((option) => option === value) ?? "";
}

type FormFields = {
  seller_type: "private" | "company";
  make_mode: "catalog" | "manual";
  model_mode: "catalog" | "manual";
  make_id: string;
  model_id: string;
  manual_make: string;
  manual_model: string;
  generation_id: string;
  modification_id: string;
  body_type_id: string;
  body_variant_id: string;
  year: string;
  mileage_km: string;
  fuel: NonNullable<ListingDraftInput["fuel"]> | "";
  transmission: NonNullable<ListingDraftInput["transmission"]> | "";
  drive: NonNullable<ListingDraftInput["drive"]> | "";
  engine_volume_l: string;
  power_hp: string;
  condition: NonNullable<ListingDraftInput["condition"]> | "";
  color: NonNullable<ListingDraftInput["color"]> | "";
  customs_status: NonNullable<ListingDraftInput["customs_status"]> | "";
  technical_condition: NonNullable<ListingDraftInput["technical_condition"]> | "";
  body_condition: NonNullable<ListingDraftInput["body_condition"]> | "";
  exchange: boolean;
  bargaining: boolean;
  credit: boolean;
  leasing: boolean;
  equipment: string[];
  district: string;
  call_hours: string;
  damaged: boolean;
  parts_only: boolean;
  vin: string;
  description: string;
  price_amount: string;
  currency: "BYN" | "USD";
  region_id: string;
  city_mode: "catalog" | "manual";
  city_id: string;
  manual_city: string;
  contact_phone: string;
};

function initialFields(listing: Listing | null): FormFields {
  const manualMake = listing?.make?.slug.startsWith("manual-") || false;
  const manualModel = manualMake || listing?.model?.slug.startsWith("manual-") || false;
  return {
    seller_type: listing?.seller.type || "private",
    make_mode: manualMake ? "manual" : "catalog",
    model_mode: manualModel ? "manual" : "catalog",
    make_id: manualMake ? "" : listing?.make?.id || "",
    model_id: manualModel ? "" : listing?.model?.id || "",
    manual_make: manualMake ? listing?.make?.name || "" : "",
    manual_model: manualModel ? listing?.model?.name || "" : "",
    generation_id: manualModel ? "" : listing?.generation?.id || "",
    modification_id: manualModel ? "" : listing?.modification_id || listing?.modification?.id || "",
    body_type_id: "",
    body_variant_id: manualModel ? "" : listing?.body_variant_id || listing?.body_variant?.id || "",
    year: listing?.year ? String(listing.year) : "",
    mileage_km: listing?.mileage_km != null ? String(listing.mileage_km) : "",
    fuel: enumValue(listing?.fuel, FUEL_OPTIONS),
    transmission: enumValue(listing?.transmission, TRANSMISSION_OPTIONS),
    drive: enumValue(listing?.drive, DRIVE_OPTIONS),
    engine_volume_l: listing?.engine_volume_l || "",
    power_hp: listing?.power_hp ? String(listing.power_hp) : "",
    condition: enumValue(listing?.condition || "used", CONDITION_OPTIONS),
    color: enumValue(listing?.color, ["black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "beige", "orange", "purple", "other"] as const),
    customs_status: enumValue(listing?.customs_status, ["cleared_rb", "eaeu_import", "uncleared", "unknown"] as const),
    technical_condition: enumValue(listing?.technical_condition, ["good", "needs_repair", "non_operational"] as const),
    body_condition: enumValue(listing?.body_condition, ["good", "minor_damage", "significant_damage", "repaired"] as const),
    exchange: listing?.exchange ?? false,
    bargaining: listing?.bargaining ?? false,
    credit: listing?.credit ?? false,
    leasing: listing?.leasing ?? false,
    equipment: listing?.equipment || [],
    district: listing?.district || "",
    call_hours: listing?.call_hours || "",
    damaged: listing?.damaged || false,
    parts_only: listing?.parts_only || false,
    vin: listing?.vin || "",
    description: listing?.description || "",
    price_amount: listing?.price?.amount || "",
    currency: listing?.price?.currency || "BYN",
    region_id: listing?.region?.id || "",
    city_mode: listing?.manual_city?.trim() ? "manual" : "catalog",
    city_id: listing?.city?.id || "",
    manual_city: listing?.manual_city || "",
    contact_phone: listing?.contact_phone || ""
  };
}

// The form switches between nullable catalog IDs and manually entered names.
type SellDraftPayload = Omit<Partial<ListingDraftInput>, "make_id" | "model_id"> & {
  make_id?: string | null;
  model_id?: string | null;
  manual_make?: string | null;
  manual_model?: string | null;
};

export function payloadFor(fields: FormFields): SellDraftPayload {
  const payload: SellDraftPayload = {
    seller_type: fields.seller_type,
    damaged: fields.damaged,
    parts_only: fields.parts_only,
    color: fields.color || null,
    customs_status: fields.customs_status || null,
    technical_condition: fields.technical_condition || null,
    body_condition: fields.body_condition || null,
    exchange: fields.exchange,
    bargaining: fields.bargaining,
    credit: fields.credit,
    leasing: fields.leasing,
    equipment: fields.equipment as NonNullable<ListingDraftInput["equipment"]>,
    district: fields.district.trim() || null,
    call_hours: fields.call_hours.trim() || null,
    generation_id: fields.generation_id || null,
    modification_id: fields.model_mode === "manual" ? null : fields.modification_id || null,
    body_type_id: fields.body_type_id || null,
    body_variant_id: fields.model_mode === "manual" ? null : fields.body_variant_id || null,
    description: fields.description,
    engine_volume_l: fields.engine_volume_l || null,
    power_hp: fields.power_hp ? Number(fields.power_hp) : null,
    vin: fields.vin ? fields.vin.toUpperCase() : null
  };
  payload.make_id = fields.make_mode === "manual" ? null : fields.make_id || null;
  payload.manual_make = fields.make_mode === "manual" ? fields.manual_make.trim() || null : null;
  payload.model_id = fields.model_mode === "manual" ? null : fields.model_id || null;
  payload.manual_model = fields.model_mode === "manual" ? fields.manual_model.trim() || null : null;
  if (fields.model_mode === "manual") payload.generation_id = null;
  payload.city_id = fields.city_mode === "manual" ? null : fields.city_id || null;
  payload.manual_city = fields.city_mode === "manual" ? fields.manual_city.trim() || null : null;
  if (fields.year) payload.year = Number(fields.year);
  if (fields.mileage_km) payload.mileage_km = Number(fields.mileage_km);
  if (fields.fuel) payload.fuel = fields.fuel;
  if (fields.transmission) payload.transmission = fields.transmission;
  if (fields.drive) payload.drive = fields.drive;
  if (fields.condition) payload.condition = fields.condition;
  if (fields.price_amount) payload.price = { amount: fields.price_amount, currency: fields.currency };
  if (fields.region_id) payload.region_id = fields.region_id;
  if (fields.contact_phone) payload.contact_phone = fields.contact_phone;
  return payload;
}

function errorMessage(error: unknown) {
  if (error instanceof ApiClientError && error.status === 409) return "Черновик изменился. Обновите страницу и повторите попытку.";
  return error instanceof Error ? error.message : "Не удалось сохранить данные";
}

function catalogRequestStatusLabel(status: CatalogRequest["status"]) {
  if (status === "pending") return "Ожидает проверки";
  if (status === "resolved") return "Найден вариант";
  return "Отклонён";
}

function createIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

type FieldErrorKey = keyof FormFields | "photos";
type FieldErrors = Partial<Record<FieldErrorKey, string>>;
type StepValidationError = {
  message: string;
  fields: FieldErrorKey[];
  focusField?: FieldErrorKey;
  messages?: FieldErrors;
};

const fieldErrorLabels: Partial<Record<FieldErrorKey, string>> = {
  seller_type: "кто продаёт",
  make_id: "марку",
  manual_make: "марку",
  model_id: "модель",
  manual_model: "модель",
  generation_id: "поколение",
  body_type_id: "тип кузова",
  body_variant_id: "вариант кузова",
  modification_id: "модификацию",
  year: "год выпуска",
  mileage_km: "пробег",
  fuel: "топливо",
  transmission: "коробку передач",
  drive: "привод",
  engine_volume_l: "объём двигателя",
  power_hp: "мощность",
  condition: "состояние",
  description: "описание",
  vin: "VIN",
  price_amount: "цену",
  region_id: "область",
  city_id: "населённый пункт",
  manual_city: "населённый пункт",
  contact_phone: "контактный телефон",
  photos: "фотографии"
};

const localFieldMessages: Partial<Record<FieldErrorKey, string>> = {
  seller_type: "Выберите тип продавца.",
  make_id: "Выберите марку из каталога.",
  manual_make: "Укажите марку автомобиля.",
  model_id: "Выберите модель из каталога.",
  manual_model: "Укажите модель автомобиля.",
  year: "Укажите корректный год выпуска.",
  mileage_km: "Укажите целое число от 0 до 5 000 000 км.",
  fuel: "Выберите топливо.",
  transmission: "Выберите коробку передач.",
  drive: "Выберите привод.",
  condition: "Выберите состояние автомобиля.",
  description: "Добавьте описание автомобиля.",
  price_amount: "Укажите цену больше нуля.",
  region_id: "Выберите область.",
  city_id: "Выберите населённый пункт из списка.",
  manual_city: "Укажите населённый пункт.",
  contact_phone: "Укажите контактный телефон.",
  photos: "Добавьте хотя бы одну обработанную фотографию."
};

const fieldSteps: Partial<Record<FieldErrorKey, number>> = {
  seller_type: 1,
  condition: 1,
  make_id: 2,
  manual_make: 2,
  model_id: 2,
  manual_model: 2,
  generation_id: 2,
  body_type_id: 2,
  body_variant_id: 2,
  modification_id: 2,
  year: 2,
  mileage_km: 2,
  fuel: 2,
  transmission: 2,
  drive: 2,
  engine_volume_l: 2,
  power_hp: 2,
  description: 3,
  vin: 3,
  price_amount: 4,
  region_id: 4,
  city_id: 4,
  manual_city: 4,
  contact_phone: 4,
  photos: 5
};

function safeFieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiClientError)) return {};
  const knownFields = new Set(Object.keys(fieldErrorLabels));
  return Object.entries(error.fieldErrors).reduce<FieldErrors>((result, [field, value]) => {
    if (!knownFields.has(field) || typeof value !== "string") return result;
    const message = value.replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 240);
    if (message) result[field as FieldErrorKey] = message;
    return result;
  }, {});
}

function mileageErrorFor(value: string) {
  if (!value.trim()) return "Укажите пробег автомобиля.";
  const mileage = Number(value);
  return Number.isInteger(mileage) && mileage >= 0 && mileage <= 5_000_000
    ? ""
    : "Укажите целое число от 0 до 5 000 000 км.";
}

function pause(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeCatalogValue(value: string) {
  return value.trim().toLocaleLowerCase("ru-RU").replace(/ё/g, "е").replace(/\s*\/\s*/g, "/").replace(/\s+/g, " ");
}

const fuelValues: Record<string, string> = {
  petrol: "petrol", gasoline: "petrol", бензин: "petrol", бензиновый: "petrol",
  diesel: "diesel", дизель: "diesel", дизельный: "diesel",
  hybrid: "hybrid", гибрид: "hybrid", гибридный: "hybrid",
  electric: "electric", electricity: "electric", электро: "electric", электричество: "electric", электрический: "electric",
  lpg: "lpg", cng: "lpg", газ: "lpg", "газ/бензин": "lpg", газовый: "lpg", гбо: "lpg", "сжиженный газ": "lpg", "пропан-бутан": "lpg", метан: "lpg",
  other: "other", другое: "other", прочее: "other"
};

const transmissionValues: Record<string, string> = {
  manual: "manual", "механика": "manual", "механическая": "manual", мкпп: "manual",
  automatic: "automatic", "автомат": "automatic", "автоматическая": "automatic", акпп: "automatic",
  robot: "robot", робот: "robot", роботизированная: "robot", ркпп: "robot", dct: "robot", dsg: "robot",
  cvt: "cvt", "вариатор": "cvt", "вариатор (cvt)": "cvt", "бесступенчатая": "cvt",
  other: "other", другое: "other", прочее: "other"
};

const driveValues: Record<string, string> = {
  front: "front", fwd: "front", ff: "front", "передний": "front", "передний привод": "front", переднеприводный: "front",
  rear: "rear", rwd: "rear", fr: "rear", "задний": "rear", "задний привод": "rear", заднеприводный: "rear",
  "задний привод, двигатель посередине": "rear", "задний привод, заднее расположение двигателя": "rear",
  all: "all", awd: "all", "4wd": "all", "4x4": "all", quattro: "all", xdrive: "all", "4matic": "all",
  "полный": "all", "полный привод": "all", "полный привод (4wd)": "all", "постоянный полный привод": "all", "подключаемый полный привод": "all",
  other: "other", другое: "other", прочее: "other"
};

const reviewFuelLabels: Record<string, string> = {
  petrol: "Бензин", diesel: "Дизель", hybrid: "Гибрид", electric: "Электро", lpg: "Газ", other: "Другое"
};

const reviewTransmissionLabels: Record<string, string> = {
  manual: "Механика", automatic: "Автомат", robot: "Робот", cvt: "Вариатор", other: "Другое"
};

const reviewDriveLabels: Record<string, string> = {
  front: "Передний", rear: "Задний", all: "Полный", other: "Другое"
};

function mappedCatalogValue(value: string | null | undefined, values: Record<string, string>) {
  return value ? values[normalizeCatalogValue(value)] : undefined;
}

function engineVolumeForInput(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value) || value < 0 || value > 20) return undefined;
  const rounded = Math.round(value * 10) / 10;
  return Math.abs(value - rounded) < 0.0000001 ? rounded.toFixed(1) : undefined;
}

function powerForInput(value: number | null | undefined) {
  return value != null && Number.isInteger(value) && value >= 1 && value <= 2500 ? String(value) : undefined;
}

function safeSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

export function SellForm({ initialListing = null, makes, models: initialModels, generations: initialGenerations, bodyTypes, regions, cities: initialCities, company }: {
  initialListing?: Listing | null;
  makes: CatalogItem[];
  models: CatalogItem[];
  generations: CatalogItem[];
  bodyTypes: CatalogItem[];
  regions: CatalogItem[];
  cities: CatalogItem[];
  company: Company | null;
}) {
  const router = useRouter();
  const firstFields = useMemo(() => ({ ...initialFields(initialListing), body_type_id: bodyTypes.find((item) => item.name === initialListing?.body_type)?.id || "" }), [initialListing, bodyTypes]);
  const [fields, setFields] = useState(firstFields);
  const [missingModificationSelected, setMissingModificationSelected] = useState(false);
  const [manualModificationName, setManualModificationName] = useState("");
  const [catalogRequestNote, setCatalogRequestNote] = useState("");
  const [catalogRequests, setCatalogRequests] = useState<CatalogRequest[]>([]);
  const [catalogRequestsLoading, setCatalogRequestsLoading] = useState(false);
  const [catalogRequestsError, setCatalogRequestsError] = useState("");
  const [catalogRequestMessage, setCatalogRequestMessage] = useState("");
  const [catalogRequestSubmitting, setCatalogRequestSubmitting] = useState(false);
  const catalogRequestKey = useRef<{ payload: string; key: string } | null>(null);
  const [models, setModels] = useState(initialModels);
  const [generations, setGenerations] = useState(initialGenerations);
  const [modifications, setModifications] = useState<CatalogModification[]>([]);
  const [modificationsLoading, setModificationsLoading] = useState(false);
  const [bodyVariants, setBodyVariants] = useState<CatalogItem[]>([]);
  const [bodyVariantsLoading, setBodyVariantsLoading] = useState(false);
  const [bodyVariantsError, setBodyVariantsError] = useState(false);
  const [cities, setCities] = useState(initialCities);
  const [listingOptions, setListingOptions] = useState<ListingOptions | null>(null);
  const [listingOptionsError, setListingOptionsError] = useState(false);
  const [validationPolicy, setValidationPolicy] = useState<ListingValidationPolicy | null>(null);
  const [validationPolicyLoading, setValidationPolicyLoading] = useState(true);
  const [validationPolicyError, setValidationPolicyError] = useState(false);
  const [validationPolicyRetry, setValidationPolicyRetry] = useState(0);
  const [draft, setDraft] = useState<Listing | null>(initialListing);
  const draftRef = useRef<Listing | null>(initialListing);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const savedSnapshot = useRef(initialListing ? JSON.stringify(payloadFor(firstFields)) : "");
  const [step, setStep] = useState(1);
  const [photos, setPhotos] = useState<ListingPhoto[]>(initialListing?.photos || []);
  const [saveState, setSaveState] = useState(initialListing ? "saved" : "unsaved");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const lastFocusedStep = useRef(step);
  const mileageInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (lastFocusedStep.current === step) return;
    lastFocusedStep.current = step;
    stepHeadingRef.current?.focus();
  }, [step]);

  useEffect(() => { draftRef.current = draft; }, [draft]);
  const loadCatalogRequests = useCallback(async (listingId: string) => {
    setCatalogRequestsLoading(true);
    setCatalogRequestsError("");
    try {
      const result = await catalogRequestsApi.listForListing(listingId);
      setCatalogRequests(result.items);
    } catch {
      setCatalogRequestsError("Не удалось загрузить статус запроса каталога.");
    } finally {
      setCatalogRequestsLoading(false);
    }
  }, []);
  useEffect(() => {
    if (!draft?.id) {
      setCatalogRequests([]);
      setCatalogRequestsError("");
      return;
    }
    void loadCatalogRequests(draft.id);
  }, [draft?.id, loadCatalogRequests]);
  useEffect(() => {
    let active = true;
    api.listingOptions().then((options) => { if (active) { setListingOptions(options); setListingOptionsError(false); } })
      .catch(() => { if (active) setListingOptionsError(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setValidationPolicyLoading(true);
    setValidationPolicyError(false);
    api.listingValidationPolicy()
      .then((policy) => {
        if (!active) return;
        setValidationPolicy(policy);
        setFieldErrors((current) => {
          const next = { ...current };
          let changed = false;
          for (const field of ["year", "photos"] as const) {
            if (next[field]?.includes("правила подачи")) {
              delete next[field];
              changed = true;
            }
          }
          return changed ? next : current;
        });
      })
      .catch(() => { if (active) { setValidationPolicy(null); setValidationPolicyError(true); } })
      .finally(() => { if (active) setValidationPolicyLoading(false); });
    return () => { active = false; };
  }, [validationPolicyRetry]);

  useEffect(() => {
    let active = true;
    if (!fields.make_id) { setModels([]); return () => { active = false; }; }
    api.catalog("models", { make_id: fields.make_id })
      .then((result) => { if (active) setModels(result.items); })
      .catch(() => { if (active) setModels(fields.make_id === initialListing?.make?.id ? initialModels : []); });
    return () => { active = false; };
  }, [fields.make_id, initialListing, initialModels]);
  useEffect(() => {
    let active = true;
    if (!fields.model_id) { setGenerations([]); return () => { active = false; }; }
    api.catalog("generations", { model_id: fields.model_id })
      .then((result) => { if (active) setGenerations(result.items); })
      .catch(() => { if (active) setGenerations(fields.model_id === initialListing?.model?.id ? initialGenerations : []); });
    return () => { active = false; };
  }, [fields.model_id, initialListing, initialGenerations]);
  useEffect(() => {
    let active = true;
    if (fields.model_mode !== "catalog" || !fields.generation_id) {
      setModifications([]);
      setModificationsLoading(false);
      return () => { active = false; };
    }
    setModificationsLoading(true);
    api.catalog("modifications", { generation_id: fields.generation_id })
      .then((result) => {
        if (!active) return;
        const items = result.items as CatalogModification[];
        const savedModification = initialListing?.modification;
        const savedGenerationId = initialListing?.generation?.id;
        setModifications(savedModification && fields.generation_id === savedGenerationId && !items.some((item) => item.id === savedModification.id)
          ? [savedModification, ...items]
          : items);
      })
      .catch(() => { if (active) setModifications([]); })
      .finally(() => { if (active) setModificationsLoading(false); });
    return () => { active = false; };
  }, [fields.generation_id, fields.model_mode, initialListing]);
  useEffect(() => {
    let active = true;
    if (fields.model_mode !== "catalog" || !fields.generation_id) {
      setBodyVariants([]);
      setBodyVariantsLoading(false);
      setBodyVariantsError(false);
      return () => { active = false; };
    }
    setBodyVariants([]);
    setBodyVariantsLoading(true);
    setBodyVariantsError(false);
    api.catalog("body-variants", { generation_id: fields.generation_id })
      .then((result) => {
        if (!active) return;
        const items = result.items;
        const savedVariant = initialListing?.body_variant;
        const savedVariantId = initialListing?.body_variant_id || savedVariant?.id;
        const savedGenerationId = initialListing?.generation?.id;
        setBodyVariants(savedVariant && savedVariant.id === savedVariantId && fields.generation_id === savedGenerationId && !items.some((item) => item.id === savedVariant.id)
          ? [savedVariant, ...items]
          : items);
      })
      .catch(() => {
        if (!active) return;
        const savedVariant = initialListing?.body_variant;
        const savedVariantId = initialListing?.body_variant_id || savedVariant?.id;
        setBodyVariants(savedVariant && savedVariant.id === savedVariantId && initialListing?.generation?.id === fields.generation_id ? [savedVariant] : []);
        setBodyVariantsError(true);
      })
      .finally(() => { if (active) setBodyVariantsLoading(false); });
    return () => { active = false; };
  }, [fields.generation_id, fields.model_mode, initialListing]);
  useEffect(() => {
    let active = true;
    if (!fields.region_id) { setCities([]); return () => { active = false; }; }
    api.cities(fields.region_id)
      .then((result) => { if (active) setCities(result.items); })
      .catch(() => { if (active) setCities(fields.region_id === initialListing?.region?.id ? initialCities : []); });
    return () => { active = false; };
  }, [fields.region_id, initialListing, initialCities]);

  function clearFieldErrors(...keys: FieldErrorKey[]) {
    if (!keys.length) return;
    setFieldErrors((current) => {
      let changed = false;
      const next = { ...current };
      for (const key of keys) {
        if (!(key in next)) continue;
        delete next[key];
        changed = true;
      }
      return changed ? next : current;
    });
  }

  function focusField(field: FieldErrorKey | undefined) {
    if (!field) return;
    if (field === "mileage_km") {
      mileageInputRef.current?.focus();
      return;
    }
    document.getElementById(field)?.focus();
  }

  function applyValidationError(validation: StepValidationError) {
    const next: FieldErrors = {};
    for (const field of validation.fields) next[field] = validation.messages?.[field] || localFieldMessages[field] || validation.message;
    setFieldErrors(next);
    setError("");
    focusField(validation.focusField || validation.fields[0]);
  }

  function applyIssue(issue: unknown) {
    const next = safeFieldErrors(issue);
    if (Object.keys(next).length) {
      setFieldErrors(next);
      setError("");
      const firstField = Object.keys(next)[0] as FieldErrorKey;
      const targetStep = fieldSteps[firstField];
      if (targetStep && targetStep !== step) setStep(targetStep);
      else focusField(firstField);
      return;
    }
    setFieldErrors({});
    setError(errorMessage(issue));
  }

  function fieldErrorId(field: FieldErrorKey) {
    return field === "mileage_km" ? "mileage-error" : `${field}-error`;
  }

  function fieldProps(field: FieldErrorKey) {
    const message = fieldErrors[field];
    return {
      id: field,
      "aria-invalid": message ? ("true" as const) : undefined,
      "aria-describedby": message ? fieldErrorId(field) : undefined
    };
  }

  function fieldError(field: FieldErrorKey) {
    const message = fieldErrors[field];
    return message ? <small className="inline-error" id={fieldErrorId(field)} role="alert">{message}</small> : null;
  }

  async function queueSave(payload: SellDraftPayload) {
    const snapshot = JSON.stringify(payload);
    if (snapshot === savedSnapshot.current) return saveQueue.current;
    setSaveState("saving");
    const currentQueue = saveQueue.current.catch(() => undefined).then(async () => {
      const current = draftRef.current;
      if (!current || snapshot === savedSnapshot.current) return;
      const result = await api.updateDraft(current.id, current.revision, payload as Partial<ListingDraftInput>);
      draftRef.current = result.listing;
      setDraft(result.listing);
      savedSnapshot.current = snapshot;
      setSaveState("saved");
    }).catch((issue) => {
      setSaveState("error");
      applyIssue(issue);
      throw issue;
    });
    saveQueue.current = currentQueue;
    return currentQueue;
  }

  const currentSnapshot = JSON.stringify(payloadFor(fields));
  useEffect(() => {
    if (!draftRef.current || currentSnapshot === savedSnapshot.current) return;
    const timer = setTimeout(() => { void queueSave(payloadFor(fields)).catch(() => undefined); }, 750);
    return () => clearTimeout(timer);
  }, [currentSnapshot]);

  function update<K extends keyof FormFields>(key: K, value: FormFields[K]) {
    setError("");
    clearFieldErrors(key);
    setFields((current) => ({ ...current, [key]: value }));
  }

  function changeMake(makeId: string) {
    setError("");
    clearFieldErrors("make_id", "model_id", "manual_model", "generation_id", "modification_id", "body_variant_id");
    setBodyVariants([]);
    setFields((current) => ({
      ...current,
      make_id: makeId,
      model_id: "",
      manual_model: "",
      generation_id: "",
      modification_id: "",
      body_variant_id: ""
    }));
  }

  function changeModel(modelId: string) {
    setError("");
    clearFieldErrors("model_id", "generation_id", "modification_id", "body_variant_id");
    setBodyVariants([]);
    setFields((current) => ({ ...current, model_id: modelId, generation_id: "", modification_id: "", body_variant_id: "" }));
  }

  function changeMakeMode(mode: FormFields["make_mode"]) {
    setError("");
    clearFieldErrors("make_id", "manual_make", "model_id", "manual_model", "generation_id", "modification_id", "body_variant_id");
    setBodyVariants([]);
    setMissingModificationSelected(false);
    setFields((current) => ({
      ...current,
      make_mode: mode,
      model_mode: mode === "manual" ? "manual" : "catalog",
      make_id: "",
      model_id: "",
      manual_make: "",
      manual_model: "",
      generation_id: "",
      modification_id: "",
      body_variant_id: ""
    }));
  }

  function changeModelMode(mode: FormFields["model_mode"]) {
    setError("");
    clearFieldErrors("model_id", "manual_model", "generation_id", "modification_id", "body_variant_id");
    setBodyVariants([]);
    setMissingModificationSelected(false);
    setFields((current) => ({
      ...current,
      model_mode: mode,
      model_id: "",
      manual_model: "",
      generation_id: "",
      modification_id: "",
      body_variant_id: ""
    }));
  }

  function changeCityMode(mode: FormFields["city_mode"]) {
    setError("");
    clearFieldErrors("city_id", "manual_city");
    setFields((current) => ({ ...current, city_mode: mode, city_id: "", manual_city: "" }));
  }

  function changeRegion(regionId: string) {
    setError("");
    clearFieldErrors("region_id", "city_id", "manual_city");
    setFields((current) => ({ ...current, region_id: regionId, city_id: "", manual_city: "" }));
  }

  function changeGeneration(generationId: string) {
    setError("");
    clearFieldErrors("generation_id", "modification_id", "body_variant_id");
    setBodyVariants([]);
    setMissingModificationSelected(false);
    setFields((current) => ({ ...current, generation_id: generationId, modification_id: "", body_variant_id: "" }));
  }

  function changeModification(modificationId: string) {
    const modification = modifications.find((item) => item.id === modificationId)
      || (initialListing?.modification?.id === modificationId ? initialListing.modification : undefined);
    setError("");
    setMissingModificationSelected(false);
    clearFieldErrors("modification_id", "engine_volume_l", "power_hp", "fuel", "transmission", "drive");
    setFields((current) => {
      const next = { ...current, modification_id: modificationId };
      const specs = modification?.source ? modification.specs : undefined;
      if (!specs) return next;

      const engineVolume = engineVolumeForInput(specs.engine_l);
      const power = powerForInput(specs.power_hp);
      const fuel = enumValue(mappedCatalogValue(specs.fuel, fuelValues), FUEL_OPTIONS);
      const transmission = enumValue(mappedCatalogValue(specs.transmission, transmissionValues), TRANSMISSION_OPTIONS);
      const drive = enumValue(mappedCatalogValue(specs.drive, driveValues), DRIVE_OPTIONS);
      if (engineVolume !== undefined) next.engine_volume_l = engineVolume;
      if (power !== undefined) next.power_hp = power;
      if (fuel) next.fuel = fuel;
      if (transmission) next.transmission = transmission;
      if (drive) next.drive = drive;
      return next;
    });
  }

  async function submitCatalogRequest() {
    const requestedName = manualModificationName.trim();
    if (!requestedName) {
      setCatalogRequestMessage("Укажите название модификации, которую не нашли.");
      return;
    }
    const current = draftRef.current;
    if (!current) {
      setCatalogRequestMessage("Сначала сохраните черновик объявления.");
      return;
    }
    if (catalogRequests.some((item) => item.status === "pending")) {
      setCatalogRequestMessage("У этого объявления уже есть запрос на проверке.");
      return;
    }

    setCatalogRequestSubmitting(true);
    setCatalogRequestMessage("");
    setCatalogRequestsError("");
    try {
      await queueSave(payloadFor(fields));
      const latest = draftRef.current;
      if (!latest) throw new Error("Не удалось прочитать сохранённый черновик.");
      const payload = {
        expected_listing_revision: latest.revision,
        manual_modification_name: requestedName,
        note: catalogRequestNote.trim() || null,
      };
      const payloadDigest = JSON.stringify(payload);
      if (!catalogRequestKey.current || catalogRequestKey.current.payload !== payloadDigest) {
        catalogRequestKey.current = { payload: payloadDigest, key: createIdempotencyKey() };
      }
      const result = await catalogRequestsApi.createForListing(latest.id, payload, catalogRequestKey.current.key);
      setCatalogRequests((items) => [result.request, ...items.filter((item) => item.id !== result.request.id)]);
      setCatalogRequestMessage("Запрос отправлен в справочник.");
      catalogRequestKey.current = null;
    } catch (issue) {
      setCatalogRequestMessage(issue instanceof ApiClientError && issue.status === 409
        ? "Черновик или запрос изменился. Обновите статус и повторите отправку."
        : "Не удалось отправить запрос. Проверьте соединение и повторите попытку.");
    } finally {
      setCatalogRequestSubmitting(false);
    }
  }

  function validateStep(target: number, photoState: ListingPhoto[] = photos): StepValidationError | null {
    if (target === 1 && fields.seller_type === "company" && company?.status !== "approved") return { message: "Чтобы публиковать от имени компании, дождитесь её допуска.", fields: ["seller_type"], focusField: "seller_type" };
    if (target === 2) {
      if (!validationPolicy) {
        const message = validationPolicyLoading
          ? "Дождитесь загрузки правил подачи."
          : "Не удалось загрузить правила подачи. Повторите загрузку, чтобы продолжить.";
        return { message, fields: ["year"], focusField: "year", messages: { year: message } };
      }
      const hasMake = fields.make_mode === "manual" ? Boolean(fields.manual_make.trim()) : Boolean(fields.make_id);
      const hasModel = fields.model_mode === "manual" ? Boolean(fields.manual_model.trim()) : Boolean(fields.model_id);
      const missingCatalogFields: FieldErrorKey[] = [];
      if (!hasMake) missingCatalogFields.push(fields.make_mode === "manual" ? "manual_make" : "make_id");
      if (!hasModel) missingCatalogFields.push(fields.model_mode === "manual" ? "manual_model" : "model_id");
      if (missingCatalogFields.length) return { message: "Выберите марку и модель из каталога или укажите вручную.", fields: missingCatalogFields, focusField: missingCatalogFields[0] };
      const year = Number(fields.year);
      const maximumYear = fields.condition === "new" ? validationPolicy.new_year_max : validationPolicy.used_year_max;
      if (!Number.isInteger(year) || year < validationPolicy.listing_year_min || year > maximumYear) {
        const message = !Number.isInteger(year)
          ? "Укажите корректный год выпуска."
          : `Год выпуска должен быть от ${validationPolicy.listing_year_min} до ${maximumYear}.`;
        return { message, fields: ["year"], focusField: "year", messages: { year: message } };
      }
      const mileageError = mileageErrorFor(fields.mileage_km);
      if (mileageError) return { message: mileageError, fields: ["mileage_km"], focusField: "mileage_km", messages: { mileage_km: mileageError } };
      const missingTechnicalFields: FieldErrorKey[] = [];
      if (!fields.fuel) missingTechnicalFields.push("fuel");
      if (!fields.transmission) missingTechnicalFields.push("transmission");
      if (!fields.drive) missingTechnicalFields.push("drive");
      if (missingTechnicalFields.length) return { message: "Укажите топливо, коробку передач и привод.", fields: missingTechnicalFields, focusField: missingTechnicalFields[0] };
    }
    if (target === 3) {
      if (!fields.condition) return { message: "Выберите состояние автомобиля.", fields: ["condition"], focusField: "condition" };
      if (!fields.description.trim()) return { message: "Добавьте описание автомобиля.", fields: ["description"], focusField: "description" };
    }
    if (target === 4) {
      if (!fields.price_amount || Number(fields.price_amount) <= 0) return { message: "Укажите цену больше нуля.", fields: ["price_amount"], focusField: "price_amount" };
      if (!fields.region_id) return { message: "Выберите область.", fields: ["region_id"], focusField: "region_id" };
      if (fields.city_mode === "manual" ? !fields.manual_city.trim() : !fields.city_id) {
        const cityField = fields.city_mode === "manual" ? "manual_city" : "city_id";
        return { message: "Выберите населённый пункт из списка или укажите вручную.", fields: [cityField], focusField: cityField };
      }
      if (!fields.contact_phone.trim()) return { message: "Укажите контактный телефон.", fields: ["contact_phone"], focusField: "contact_phone" };
    }
    if (target === 5) {
      if (!validationPolicy) {
        const message = validationPolicyLoading
          ? "Дождитесь загрузки правил подачи."
          : "Не удалось загрузить правила подачи. Повторите загрузку, чтобы продолжить.";
        return { message, fields: ["photos"], focusField: "photos", messages: { photos: message } };
      }
      const minimum = minimumPhotoCount(validationPolicy, fields);
      const readyPhotoCount = photoState.filter((photo) => photo.status === "ready").length;
      if (readyPhotoCount < minimum) {
        const message = `Добавьте минимум ${minimum} ${photoCountPhrase(minimum)}.`;
        return { message, fields: ["photos"], focusField: "photos", messages: { photos: message } };
      }
      if (photoState.some((photo) => photo.status === "failed")) {
        const message = "Удалите фотографии с ошибкой обработки и загрузите их снова.";
        return { message, fields: ["photos"], focusField: "photos", messages: { photos: message } };
      }
      if (photoState.some((photo) => photo.status === "queued" || photo.status === "processing")) {
        const message = "Дождитесь завершения обработки фотографий.";
        return { message, fields: ["photos"], focusField: "photos", messages: { photos: message } };
      }
    }
    return null;
  }

  async function nextStep() {
    const validation = validateStep(step);
    if (validation) {
      applyValidationError(validation);
      return;
    }
    setError("");
    setFieldErrors({});
    setBusy(true);
    try {
      const payload = payloadFor(fields);
      let current = draftRef.current;
      if (!current) {
        setSaveState("saving");
        const result = await api.createDraft(payload as Partial<ListingDraftInput>);
        current = result.listing;
        draftRef.current = current;
        setDraft(current);
        savedSnapshot.current = JSON.stringify(payload);
      } else {
        await queueSave(payload);
      }
      if (step === 5) {
        const refreshedPhotos = await refreshPhotos(current.id);
        const photoValidation = validateStep(5, refreshedPhotos);
        if (photoValidation) {
          applyValidationError(photoValidation);
          return;
        }
      }
      setStep((value) => Math.min(6, value + 1));
    } catch (issue) {
      applyIssue(issue);
    } finally {
      setBusy(false);
    }
  }

  function previousStep() { setError(""); setFieldErrors({}); setStep((value) => Math.max(1, value - 1)); }

  async function refreshPhotos(id: string): Promise<ListingPhoto[]> {
    const response = await api.photos(id);
    setPhotos(response.items);
    try {
      const latest = (await api.listing(id)).listing;
      draftRef.current = latest;
      setDraft(latest);
    } catch { /* Photo state remains available even if the listing refresh fails. */ }
    return response.items;
  }

  async function uploadSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = "";
    if (!draftRef.current) { setError("Сначала сохраните черновик."); return; }
    if (!validationPolicy) { setError("Сначала загрузите правила подачи."); return; }
    if (photos.length + files.length > validationPolicy.maximum_photos) {
      setError(`На одно объявление можно добавить не более ${validationPolicy.maximum_photos} фотографий.`);
      return;
    }
    const tooLarge = files.find((file) => file.size > 20 * 1024 * 1024);
    if (tooLarge) { setError(`${tooLarge.name}: максимальный размер файла — 20 MiB.`); return; }
    if (!files.length) return;

    setError("");
    setBusy(true);
    const work = [...files];
    const workers = Array.from({ length: Math.min(2, work.length) }, async () => {
      while (work.length) {
        const file = work.shift();
        const current = draftRef.current;
        if (!file || !current) return;
        try {
          const photo = await api.uploadPhoto(current.id, file);
          if (photo.status === "failed") setError(`${file.name}: сервер не смог обработать файл.`);
        } catch (issue) {
          const next = safeFieldErrors(issue);
          if (Object.keys(next).length) setFieldErrors(next);
          setError(Object.keys(next).length ? "" : `${file.name}: ${errorMessage(issue)}`);
        }
      }
    });
    await Promise.all(workers);
    try { await pollPhotos(draftRef.current!.id); } catch (issue) { applyIssue(issue); }
    setBusy(false);
  }

  async function pollPhotos(id: string) {
    let items: ListingPhoto[] = [];
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const response = await api.photos(id);
      items = response.items;
      setPhotos(items);
      if (!items.some((photo) => photo.status === "queued" || photo.status === "processing")) break;
      await pause(1000);
    }
    await refreshPhotos(id);
  }

  async function removePhoto(photoId: string) {
    const current = draftRef.current;
    if (!current) return;
    setBusy(true); setError("");
    try { await api.deletePhoto(current.id, photoId); await refreshPhotos(current.id); }
    catch (issue) { applyIssue(issue); }
    finally { setBusy(false); }
  }

  async function chooseCover(photoId: string) {
    const current = draftRef.current;
    if (!current) return;
    setBusy(true); setError("");
    try { await api.setCover(current.id, photoId); await refreshPhotos(current.id); }
    catch (issue) { applyIssue(issue); }
    finally { setBusy(false); }
  }

  async function movePhoto(photoId: string, delta: -1 | 1) {
    const current = draftRef.current;
    if (!current) return;
    const ordered = [...photos].sort((a, b) => a.position - b.position);
    const index = ordered.findIndex((photo) => photo.id === photoId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    setBusy(true); setError("");
    try { await api.reorderPhotos(current.id, ordered.map((photo) => photo.id)); await refreshPhotos(current.id); }
    catch (issue) { applyIssue(issue); }
    finally { setBusy(false); }
  }

  async function submitListing(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validation = validateStep(2) ?? validateStep(3) ?? validateStep(4);
    if (validation) { applyValidationError(validation); return; }
    setBusy(true); setError(""); setFieldErrors({});
    try {
      const current = draftRef.current;
      if (!current) throw new Error("Сначала сохраните черновик.");
      const refreshedPhotos = await refreshPhotos(current.id);
      const photoValidation = validateStep(5, refreshedPhotos);
      if (photoValidation) {
        setStep(5);
        applyValidationError(photoValidation);
        return;
      }
      await queueSave(payloadFor(fields));
      const latest = draftRef.current;
      if (!latest) throw new Error("Не удалось прочитать сохранённый черновик.");
      await api.submitListing(latest.id, latest.revision);
      setSaveState("saved");
      router.push("/account/listings");
      router.refresh();
    } catch (issue) {
      applyIssue(issue);
    } finally {
      setBusy(false);
    }
  }

  const make = makes.find((item) => item.id === fields.make_id);
  const model = models.find((item) => item.id === fields.model_id) || initialListing?.model;
  const generation = generations.find((item) => item.id === fields.generation_id) || (initialListing?.generation?.id === fields.generation_id ? initialListing.generation : undefined);
  const selectedModification = modifications.find((item) => item.id === fields.modification_id)
    || (initialListing?.modification?.id === fields.modification_id ? initialListing.modification : undefined);
  const selectedBodyVariant = bodyVariants.find((item) => item.id === fields.body_variant_id)
    || (initialListing?.body_variant?.id === fields.body_variant_id && initialListing?.generation?.id === fields.generation_id ? initialListing.body_variant : undefined);
  const modificationSpecs = selectedModification?.specs;
  const modificationSpecRows: [string, string | number | null | undefined][] = modificationSpecs ? ([
    ["Код двигателя", modificationSpecs.engine_code],
    ["Код рамы", modificationSpecs.frame_code],
    ["Объём по каталогу, л", modificationSpecs.engine_l],
    ["Мощность по каталогу, л.с.", modificationSpecs.power_hp],
    ["Топливо по каталогу", modificationSpecs.fuel],
    ["Коробка по каталогу", modificationSpecs.transmission],
    ["Привод по каталогу", modificationSpecs.drive]
  ] as [string, string | number | null | undefined][]).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "") : [];
  const modificationPeriod = modificationSpecs?.production_period_raw;
  const modificationSummary = modificationSpecs?.summary_raw;
  const sourceUrl = selectedModification?.source?.url ? safeSourceUrl(selectedModification.source.url) : undefined;
  const hasModificationDetails = Boolean(modificationSpecRows.length || modificationPeriod?.trim() || modificationSummary?.trim());
  const bodyType = bodyTypes.find((item) => item.id === fields.body_type_id);
  const makeName = fields.make_mode === "manual" ? fields.manual_make : make?.name || initialListing?.make?.name;
  const modelName = fields.model_mode === "manual" ? fields.manual_model : model?.name || initialListing?.model?.name;
  const title = [makeName, modelName].filter(Boolean).join(" ");
  const cityName = fields.city_mode === "manual" ? fields.manual_city : cities.find((city) => city.id === fields.city_id)?.name;
  const sortedPhotos = [...photos].sort((a, b) => a.position - b.position);
  const reviewPhotos = sortedPhotos.filter((photo) => photo.status === "ready" && photo.url);
  const saveCopy = saveState === "saving" ? "Сохраняем…" : saveState === "saved" ? "Сохранено" : saveState === "error" ? "Ошибка сохранения" : "Черновик ещё не создан";

  return (
    <form className="form-page" onSubmit={submitListing}>
      <header className="page-head"><p className="eyebrow">Подача автомобиля</p><h1>{initialListing ? "Редактировать объявление" : "Новое объявление"}</h1><p role="status" aria-live="polite">Шаг {step} из 6</p></header>
      <div className="step-progress" role="progressbar" aria-label="Шаг подачи объявления" aria-valuemin={1} aria-valuemax={6} aria-valuenow={step} aria-valuetext={`Шаг ${step} из 6`}>{Array.from({ length: 6 }, (_, index) => <span key={index} className={index < step ? "is-complete" : ""} />)}</div>
      <p className={saveState === "error" ? "inline-error" : "inline-success"} role="status">{saveCopy}{draft && ` · ревизия ${draft.revision}`}</p>
      {validationPolicyLoading && <p className="muted" role="status">Загружаем правила подачи…</p>}
      {validationPolicyError && <p className="notice wide" role="alert">Не удалось загрузить правила подачи. <button className="button button-secondary button-small" type="button" onClick={() => setValidationPolicyRetry((attempt) => attempt + 1)} disabled={validationPolicyLoading}>Повторить</button></p>}

      {step === 1 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Продавец и предложение</h2>
        <label className="field"><span>Кто продаёт</span><select {...fieldProps("seller_type")} value={fields.seller_type} onChange={(event) => update("seller_type", event.target.value as FormFields["seller_type"])}>
          <option value="private">Частное лицо</option>
          <option value="company" disabled={company?.status !== "approved"}>{company?.name ? `Компания: ${company.name}` : "Компания (сначала оформите профиль)"}</option>
        </select>{fieldError("seller_type")}</label>
        <label className="field"><span>Состояние</span><select {...fieldProps("condition")} value={fields.condition} onChange={(event) => update("condition", enumValue(event.target.value, CONDITION_OPTIONS))} required><option value="new">Новый</option><option value="used">С пробегом</option></select>{fieldError("condition")}</label>
        {company && company.status !== "approved" && <p className="notice">Публикация от имени компании станет доступна после проверки её профиля.</p>}
        <fieldset className="seller-offer"><legend>Как продаётся автомобиль</legend>
          <label className="choice-card"><input type="radio" name="parts_only" checked={!fields.parts_only} onChange={() => update("parts_only", false)} /> Целиком</label>
          <label className="choice-card"><input type="radio" name="parts_only" checked={fields.parts_only} onChange={() => update("parts_only", true)} /> На запчасти</label>
        </fieldset>
      </section>}

      {step === 2 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Автомобиль и характеристики</h2><div className="form-grid">
        <label className="field"><span>Способ выбора марки</span><select aria-label="Источник марки" value={fields.make_mode} onChange={(event) => changeMakeMode(event.target.value as FormFields["make_mode"])}><option value="catalog">Из каталога</option><option value="manual">Марки нет в каталоге</option></select></label>
        {fields.make_mode === "manual" ? <label className="field"><span>Марка</span><input {...fieldProps("manual_make")} aria-label="Марка вручную" value={fields.manual_make} onChange={(event) => update("manual_make", event.target.value)} maxLength={180} required />{fieldError("manual_make")}</label> : <label className="field"><span>Марка</span><select {...fieldProps("make_id")} value={fields.make_id} onChange={(event) => changeMake(event.target.value)} required><option value="">Выберите марку</option>{makes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("make_id")}</label>}
        {fields.make_mode === "catalog" && <label className="field"><span>Способ выбора модели</span><select aria-label="Источник модели" value={fields.model_mode} onChange={(event) => changeModelMode(event.target.value as FormFields["model_mode"])} disabled={!fields.make_id}><option value="catalog">Из каталога</option><option value="manual">Модели нет в каталоге</option></select></label>}
        {fields.model_mode === "manual" ? <label className="field"><span>Модель</span><input {...fieldProps("manual_model")} aria-label="Модель вручную" value={fields.manual_model} onChange={(event) => update("manual_model", event.target.value)} maxLength={180} required />{fieldError("manual_model")}</label> : <label className="field"><span>Модель</span><select {...fieldProps("model_id")} value={fields.model_id} onChange={(event) => changeModel(event.target.value)} disabled={!models.length} required><option value="">Выберите модель</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("model_id")}</label>}
        {fields.model_mode === "catalog" && <label className="field"><span>Поколение <small className="muted">необязательно</small></span><select {...fieldProps("generation_id")} value={fields.generation_id} onChange={(event) => changeGeneration(event.target.value)} disabled={!generations.length}><option value="">Не выбрано</option>{generations.map((item) => <option key={item.id} value={item.id}>{item.name}{item.year_from ? ` · ${item.year_from}${item.year_to ? `–${item.year_to}` : ""}` : ""}</option>)}</select>{fieldError("generation_id")}</label>}
        {fields.model_mode === "catalog" && <>
          <label className="field"><span>Вариант кузова <small className="muted">необязательно</small></span><select {...fieldProps("body_variant_id")} aria-label="Вариант кузова" value={fields.body_variant_id} onChange={(event) => update("body_variant_id", event.target.value)} disabled={!fields.generation_id || bodyVariantsLoading || (!bodyVariants.length && !selectedBodyVariant)} aria-busy={bodyVariantsLoading}><option value="">{!fields.generation_id ? "Сначала выберите поколение" : bodyVariantsLoading ? "Загрузка вариантов…" : bodyVariantsError ? "Список временно недоступен" : bodyVariants.length ? "Не выбрано" : "Нет в каталоге"}</option>{fields.body_variant_id && !selectedBodyVariant && <option value={fields.body_variant_id}>Сохранённый вариант</option>}{selectedBodyVariant && !bodyVariants.some((item) => item.id === selectedBodyVariant.id) && <option value={selectedBodyVariant.id}>{selectedBodyVariant.name}</option>}{bodyVariants.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("body_variant_id")}</label>
          <label className="field"><span>Модификация <small className="muted">необязательно</small></span><select {...fieldProps("modification_id")} aria-label="Модификация" value={missingModificationSelected ? "__missing_modification__" : fields.modification_id} onChange={(event) => {
            if (event.target.value === "__missing_modification__") {
              changeModification("");
              setMissingModificationSelected(true);
              setCatalogRequestMessage("");
            } else changeModification(event.target.value);
          }} disabled={!fields.generation_id} aria-busy={modificationsLoading}>
            <option value="">{!fields.generation_id ? "Сначала выберите поколение" : modificationsLoading ? "Загрузка…" : modifications.length ? "Не выбрано" : "Нет в каталоге"}</option>
            {selectedModification && !modifications.some((item) => item.id === selectedModification.id) && <option value={selectedModification.id}>{selectedModification.name}</option>}
            {modifications.map((item) => <option key={item.id} value={item.id}>{item.name}{item.specs?.production_period_raw?.trim() ? ` · ${item.specs.production_period_raw.trim()}` : ""}</option>)}
            {fields.generation_id && <option value="__missing_modification__">Не нашёл модификацию</option>}
          </select>{fieldError("modification_id")}</label>
          {missingModificationSelected && fields.generation_id && <div className="notice wide catalog-request-intake">
            <p><strong>Сообщить о не найденной модификации</strong></p>
            <p className="muted">Сначала сохраните ручные характеристики. Запрос отправится на проверку отдельно и не задержит создание объявления.</p>
            <label className="field"><span>Название модификации</span><input aria-label="Название модификации" value={manualModificationName} onChange={(event) => { setManualModificationName(event.target.value); setCatalogRequestMessage(""); }} maxLength={180} /></label>
            <label className="field"><span>Комментарий для каталога <small className="muted">необязательно</small></span><textarea aria-label="Комментарий для каталога" value={catalogRequestNote} onChange={(event) => { setCatalogRequestNote(event.target.value); setCatalogRequestMessage(""); }} maxLength={1200} rows={3} placeholder="Опишите отличия и характеристики. Не указывайте VIN или телефон." /></label>
            <div className="form-actions">
              <button className="button button-secondary" type="button" onClick={() => void submitCatalogRequest()} disabled={catalogRequestSubmitting || busy || !manualModificationName.trim() || catalogRequests.some((item) => item.status === "pending")}>
                {catalogRequestSubmitting ? <LoaderCircle size={16} /> : <Check size={16} />} {catalogRequestSubmitting ? "Отправляем…" : catalogRequestMessage.toLowerCase().includes("не удалось отправить") ? "Повторить отправку" : "Отправить на проверку справочника"}
              </button>
            </div>
            {catalogRequestMessage && <p className={catalogRequestMessage.startsWith("Запрос отправлен") ? "inline-success" : "inline-error"} role={catalogRequestMessage.startsWith("Запрос отправлен") ? "status" : "alert"}>{catalogRequestMessage}</p>}
          </div>}
          {(catalogRequestsLoading || catalogRequestsError || catalogRequests.length > 0) && <div className="wide catalog-request-status" aria-label="Статус запросов каталога">
            {catalogRequestsLoading && <p className="muted" role="status">Загружаем статус запросов каталога…</p>}
            {catalogRequestsError && <p className="notice" role="alert">{catalogRequestsError} <button className="button button-secondary button-small" type="button" onClick={() => draft && void loadCatalogRequests(draft.id)}>Повторить</button></p>}
            {catalogRequests.map((request) => <p className="notice" key={request.id}><strong>Запрос каталога: {catalogRequestStatusLabel(request.status)}</strong>{request.manual_modification_name ? ` · ${request.manual_modification_name}` : ""}{request.resolved_modification ? ` · Рекомендация: ${request.resolved_modification.name}` : ""}{request.review_reason ? ` · ${request.review_reason}` : ""}</p>)}
          </div>}
          {selectedModification && <div className="notice wide" aria-live="polite">
            <p><strong>{selectedModification.name}</strong></p>
            {selectedModification.source && <p>Источник: {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">{selectedModification.source.name}</a> : selectedModification.source.name} · ID {selectedModification.source.id}</p>}
            {modificationSpecRows.length > 0 && <dl>{modificationSpecRows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
            {modificationPeriod?.trim() && <p><strong>Период выпуска:</strong> {modificationPeriod}</p>}
            {modificationSummary?.trim() && <p style={{ whiteSpace: "pre-wrap" }}><strong>Описание комплектации:</strong> {modificationSummary}</p>}
            {!hasModificationDetails && <p className="muted">Для этой модификации характеристики в каталоге не указаны.</p>}
          </div>}
        </>}
        {fields.model_mode === "manual" && <p className="notice wide">Марка и модель будут проверены модератором. Неизвестные характеристики оставьте пустыми.</p>}
        <label className="field"><span>Тип кузова</span><select {...fieldProps("body_type_id")} value={fields.body_type_id} onChange={(event) => update("body_type_id", event.target.value)}><option value="">Не выбрано</option>{bodyTypes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("body_type_id")}</label>
        <label className="field"><span>Год выпуска</span><input {...fieldProps("year")} type="number" inputMode="numeric" min={validationPolicy?.listing_year_min} max={validationPolicy ? (fields.condition === "new" ? validationPolicy.new_year_max : validationPolicy.used_year_max) : undefined} value={fields.year} onChange={(event) => update("year", event.target.value)} required />{fieldError("year")}</label>
        <label className="field"><span>Пробег, км</span><input {...fieldProps("mileage_km")} ref={mileageInputRef} type="number" inputMode="numeric" min="0" max="5000000" step="1" value={fields.mileage_km} onChange={(event) => update("mileage_km", event.target.value)} required />{fieldError("mileage_km")}</label>
        <label className="field"><span>Топливо</span><select {...fieldProps("fuel")} value={fields.fuel} onChange={(event) => update("fuel", enumValue(event.target.value, FUEL_OPTIONS))} required><option value="">Выберите</option><option value="petrol">Бензин</option><option value="diesel">Дизель</option><option value="hybrid">Гибрид</option><option value="electric">Электро</option><option value="lpg">Газ</option><option value="other">Другое</option></select>{fieldError("fuel")}</label>
        <label className="field"><span>Коробка передач</span><select {...fieldProps("transmission")} value={fields.transmission} onChange={(event) => update("transmission", enumValue(event.target.value, TRANSMISSION_OPTIONS))} required><option value="">Выберите</option><option value="manual">Механика</option><option value="automatic">Автомат</option><option value="robot">Робот</option><option value="cvt">Вариатор</option><option value="other">Другое</option></select>{fieldError("transmission")}</label>
        <label className="field"><span>Привод</span><select {...fieldProps("drive")} value={fields.drive} onChange={(event) => update("drive", enumValue(event.target.value, DRIVE_OPTIONS))} required><option value="">Выберите</option><option value="front">Передний</option><option value="rear">Задний</option><option value="all">Полный</option><option value="other">Другое</option></select>{fieldError("drive")}</label>
        <label className="field"><span>Объём двигателя, л</span><input {...fieldProps("engine_volume_l")} type="number" inputMode="decimal" min="0" max="20" step="0.1" value={fields.engine_volume_l} onChange={(event) => update("engine_volume_l", event.target.value)} />{fieldError("engine_volume_l")}</label>
        <label className="field"><span>Мощность, л.с.</span><input {...fieldProps("power_hp")} type="number" inputMode="numeric" min="1" max="2500" value={fields.power_hp} onChange={(event) => update("power_hp", event.target.value)} />{fieldError("power_hp")}</label>
      </div></section>}

      {step === 3 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Состояние и описание</h2><div className="form-grid">
        <label className="field"><span>Цвет</span><select value={fields.color} onChange={(event) => update("color", event.target.value as FormFields["color"])}><option value="">Не указан</option>{listingOptions?.colors.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
        <label className="field"><span>Растаможка</span><select value={fields.customs_status} onChange={(event) => update("customs_status", event.target.value as FormFields["customs_status"])}><option value="">Не указана</option>{listingOptions?.customs_statuses.map((item) => item.code !== "unknown" && <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
        <label className="field"><span>Техническое состояние</span><select value={fields.technical_condition} onChange={(event) => update("technical_condition", event.target.value as FormFields["technical_condition"])}><option value="">Не указано</option>{listingOptions?.technical_conditions.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
        <label className="field"><span>Состояние кузова</span><select value={fields.body_condition} onChange={(event) => update("body_condition", event.target.value as FormFields["body_condition"])}><option value="">Не указано</option>{listingOptions?.body_conditions.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}</select></label>
        <label className="check-field"><input type="checkbox" checked={fields.bargaining} onChange={(event) => update("bargaining", event.target.checked)} /> Возможен торг</label>
        <label className="check-field"><input type="checkbox" checked={fields.exchange} onChange={(event) => update("exchange", event.target.checked)} /> Возможен обмен</label>
        <label className="check-field"><input type="checkbox" checked={fields.credit} onChange={(event) => update("credit", event.target.checked)} /> Возможна покупка в кредит</label>
        <label className="check-field"><input type="checkbox" checked={fields.leasing} onChange={(event) => update("leasing", event.target.checked)} /> Возможен лизинг</label>
        {listingOptions && <fieldset className="equipment-options wide"><legend className="field-label">Комплектация</legend><div className="equipment-options-grid">{listingOptions.equipment.map((item) => <label className="check-field" key={item.code}><input type="checkbox" checked={fields.equipment.includes(item.code)} onChange={(event) => update("equipment", event.target.checked ? [...fields.equipment, item.code] : fields.equipment.filter((code) => code !== item.code))} /> {item.label}</label>)}</div></fieldset>}
        {listingOptionsError && <p className="notice wide" role="status">Список комплектации недоступен; можно продолжить без этих характеристик.</p>}
        <label className="field"><span>Район <small className="muted">необязательно</small></span><input maxLength={120} value={fields.district} onChange={(event) => update("district", event.target.value)} /></label>
        <label className="field"><span>Время звонков <small className="muted">необязательно</small></span><input maxLength={80} placeholder="Например, 9:00–20:00" value={fields.call_hours} onChange={(event) => update("call_hours", event.target.value)} /></label>
        <label className="check-field"><input type="checkbox" checked={fields.damaged} onChange={(event) => update("damaged", event.target.checked)} /> Есть повреждения</label>
        <label className="check-field"><input type="checkbox" checked={fields.parts_only} onChange={(event) => update("parts_only", event.target.checked)} /> Продаётся на запчасти</label>
        <label className="field wide"><span>Описание</span><textarea {...fieldProps("description")} value={fields.description} onChange={(event) => update("description", event.target.value)} maxLength={5000} placeholder="Расскажите об автомобиле, обслуживании и важных особенностях" required />{fieldError("description")}</label>
        <label className="field"><span>VIN <small className="muted">необязательно</small></span><input {...fieldProps("vin")} value={fields.vin} onChange={(event) => update("vin", event.target.value.toUpperCase())} maxLength={17} autoComplete="off" />{fieldError("vin")}</label>
      </div></section>}

      {step === 4 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Цена, расположение и контакт</h2><div className="form-grid">
        <label className="field"><span>Цена</span><input {...fieldProps("price_amount")} type="number" inputMode="decimal" min="0.01" step="0.01" value={fields.price_amount} onChange={(event) => update("price_amount", event.target.value)} required />{fieldError("price_amount")}</label>
        <label className="field"><span>Валюта</span><select value={fields.currency} onChange={(event) => update("currency", event.target.value as FormFields["currency"])}><option value="BYN">BYN</option><option value="USD">USD</option></select></label>
        <label className="field"><span>Область</span><select {...fieldProps("region_id")} value={fields.region_id} onChange={(event) => changeRegion(event.target.value)} required><option value="">Выберите область</option>{regions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("region_id")}</label>
        <label className="field"><span>Способ выбора населённого пункта</span><select aria-label="Источник населённого пункта" value={fields.city_mode} onChange={(event) => changeCityMode(event.target.value as FormFields["city_mode"])} disabled={!fields.region_id}><option value="catalog">Из справочника</option><option value="manual">Нет в справочнике</option></select></label>
        {fields.city_mode === "manual" ? <label className="field"><span>Населённый пункт</span><input {...fieldProps("manual_city")} aria-label="Населённый пункт вручную" value={fields.manual_city} onChange={(event) => update("manual_city", event.target.value)} maxLength={160} required disabled={!fields.region_id} />{fieldError("manual_city")}</label> : <label className="field"><span>Населённый пункт</span><select {...fieldProps("city_id")} value={fields.city_id} onChange={(event) => update("city_id", event.target.value)} disabled={!fields.region_id || !cities.length} required><option value="">Выберите населённый пункт</option>{cities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{fieldError("city_id")}</label>}
        <label className="field wide"><span>Телефон для связи</span><input {...fieldProps("contact_phone")} type="tel" autoComplete="tel" value={fields.contact_phone} onChange={(event) => update("contact_phone", event.target.value)} required maxLength={32} /><small className="muted">Номер не появится в выдаче. Покупатель откроет его отдельной кнопкой.</small>{fieldError("contact_phone")}</label>
      </div></section>}

      {step === 5 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Фотографии</h2><p className="muted">{validationPolicy ? `Добавьте от ${minimumPhotoCount(validationPolicy, fields)} до ${validationPolicy.maximum_photos} фотографий JPEG, PNG, WebP или HEIC. До 20 MiB на файл.` : "Правила подачи загружаются; повторите загрузку, чтобы добавить фотографии."}</p>
        {!draft && <p className="notice">Сначала перейдите с первого шага, чтобы сохранить черновик.</p>}
        <label className="button button-secondary upload-button"><ImagePlus size={18} /> Добавить фотографии<input {...fieldProps("photos")} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple disabled={busy || !draft || !validationPolicy || photos.length >= (validationPolicy?.maximum_photos ?? 0)} onChange={uploadSelected} /></label>{fieldError("photos")}
        {busy && <p className="muted" role="status"><LoaderCircle size={16} className="spin" /> Обрабатываем выбранные фотографии…</p>}
        <div className="photo-list">{sortedPhotos.map((photo, index) => <article className="photo-item" key={photo.id}>
          {photo.url ? <Image src={photo.url} alt={photo.is_cover ? "Обложка объявления" : `Фотография ${index + 1}`} width={440} height={330} unoptimized /> : <div className="photo-placeholder" aria-label="Фото обрабатывается"><LoaderCircle size={20} /></div>}
          <div className="photo-item-meta"><span className={`status-pill status-${photo.status}`}>{photo.status === "ready" ? (photo.is_cover ? "Обложка" : "Готово") : photo.status === "failed" ? "Ошибка" : "Обрабатывается"}</span>{photo.error && <small className="inline-error">{photo.error}</small>}</div>
          <div className="photo-item-controls">
            <button type="button" title="Сдвинуть влево" aria-label="Сдвинуть фото влево" disabled={busy || index === 0 || photo.status !== "ready"} onClick={() => movePhoto(photo.id, -1)}><ArrowLeft size={17} /></button>
            <button type="button" title="Сдвинуть вправо" aria-label="Сдвинуть фото вправо" disabled={busy || index === sortedPhotos.length - 1 || photo.status !== "ready"} onClick={() => movePhoto(photo.id, 1)}><ArrowRight size={17} /></button>
            <button type="button" title="Сделать обложкой" aria-label="Сделать обложкой" disabled={busy || photo.is_cover || photo.status !== "ready"} onClick={() => chooseCover(photo.id)}><Star size={16} fill={photo.is_cover ? "currentColor" : "none"} /></button>
            <button type="button" title="Удалить фото" aria-label="Удалить фото" disabled={busy} onClick={() => removePhoto(photo.id)}><Trash2 size={16} /></button>
          </div>
        </article>)}</div>
        {!photos.length && <div className="empty-state photo-empty"><p>Фотографий пока нет.</p></div>}
      </section>}

      {step === 6 && <section className="form-section"><h2 ref={stepHeadingRef} tabIndex={-1}>Проверьте объявление</h2>
        <dl className="review-list">
          <div><dt>Автомобиль</dt><dd>{title || "Выберите автомобиль"}{generation && ` · ${generation.name}`}{bodyType && ` · ${bodyType.name}`}</dd></div>
          {selectedBodyVariant && <div><dt>Вариант кузова</dt><dd>{selectedBodyVariant.name}</dd></div>}
          <div><dt>Год и пробег</dt><dd>{fields.year || "—"} · {fields.mileage_km ? `${Number(fields.mileage_km).toLocaleString("ru-BY")} км` : "—"}</dd></div>
          <div><dt>Топливо</dt><dd>{reviewFuelLabels[fields.fuel] || fields.fuel || "—"}</dd></div>
          <div><dt>Коробка передач</dt><dd>{reviewTransmissionLabels[fields.transmission] || fields.transmission || "—"}</dd></div>
          <div><dt>Привод</dt><dd>{reviewDriveLabels[fields.drive] || fields.drive || "—"}</dd></div>
          {(fields.engine_volume_l || fields.power_hp) && <div><dt>Объём двигателя и мощность</dt><dd>{[
            fields.engine_volume_l && `${fields.engine_volume_l} л`,
            fields.power_hp && `${Number(fields.power_hp).toLocaleString("ru-BY")} л.с.`
          ].filter(Boolean).join(" · ")}</dd></div>}
          <div><dt>Состояние</dt><dd>{fields.condition === "new" ? "Новый" : "С пробегом"}{fields.damaged ? " · есть повреждения" : ""}{fields.parts_only ? " · на запчасти" : ""}</dd></div>
          {(fields.color || fields.customs_status || fields.technical_condition || fields.body_condition || fields.exchange || fields.bargaining || fields.credit || fields.leasing || fields.equipment.length || fields.district || fields.call_hours) && <div><dt>Дополнительные сведения</dt><dd>{[
            listingOptions?.colors.find((option) => option.code === fields.color)?.label,
            listingOptions?.customs_statuses.find((option) => option.code === fields.customs_status)?.label,
            listingOptions?.technical_conditions.find((option) => option.code === fields.technical_condition)?.label,
            listingOptions?.body_conditions.find((option) => option.code === fields.body_condition)?.label,
            fields.exchange ? "Обмен" : "", fields.bargaining ? "Торг" : "", fields.credit ? "Кредит" : "", fields.leasing ? "Лизинг" : "",
            ...fields.equipment.map((code) => listingOptions?.equipment.find((option) => option.code === code)?.label || ""),
            fields.district, fields.call_hours
          ].filter(Boolean).join(" · ")}</dd></div>}
          <div><dt>Описание</dt><dd style={{ whiteSpace: "pre-wrap" }}>{fields.description || "—"}</dd></div>
          <div><dt>Цена</dt><dd>{fields.price_amount || "—"} {fields.currency}</dd></div>
          <div><dt>Расположение</dt><dd>{[cityName, regions.find((region) => region.id === fields.region_id)?.name].filter(Boolean).join(", ") || "—"}</dd></div>
          <div><dt>Тип продавца</dt><dd>{fields.seller_type === "company" ? "Компания" : "Частное лицо"}</dd></div>
          <div><dt>Телефон для связи</dt><dd>{fields.contact_phone || "—"}</dd></div>
          <div><dt>Фотографии</dt><dd>{photos.filter((photo) => photo.status === "ready").length} обработано</dd></div>
        </dl>
        {reviewPhotos.length > 0 && <div className="photo-list review-photo-list" role="group" aria-label="Обработанные фотографии">
          {reviewPhotos.map((photo, index) => <article className="photo-item" key={photo.id}>
            <Image src={photo.url!} alt={photo.is_cover ? "Обложка объявления" : `Фотография ${index + 1}`} width={440} height={330} unoptimized />
          </article>)}
        </div>}
        <p className="notice">После отправки объявление появится в поиске только после проверки модератором.</p>
      </section>}

      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="form-actions">
        {step > 1 ? <button className="button button-secondary" type="button" disabled={busy} onClick={previousStep}><ArrowLeft size={16} /> Назад</button> : <span />}
        {step < 6 ? <button className="button button-primary" type="button" disabled={busy} onClick={nextStep}>{busy ? "Сохраняем…" : <>Продолжить <ArrowRight size={16} /></>}</button> : <button className="button button-primary" type="submit" disabled={busy || saveState === "saving"}>{busy ? "Отправляем…" : <><Check size={17} /> Отправить на проверку</>}</button>}
      </div>
      <p className="muted autosave-note">{draft ? "Изменения черновика сохраняются автоматически." : "Черновик создаётся при переходе со следующего шага."} Контакт и VIN не сохраняются в браузере.</p>
    </form>
  );
}
