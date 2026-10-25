import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SellForm, payloadFor } from "@/components/sell-form";
import { api } from "@/lib/api";
import type { Listing } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

let container: HTMLDivElement;
let root: Root;
const policy = {
  current_year: 2026,
  listing_year_min: 1886,
  new_year_max: 2027,
  used_year_max: 2026,
  minimum_photos: { new: 1, used: 1, damaged: 1, parts: 1 },
  maximum_photos: 30,
  category_codes: ["cars", "motorcycles", "special_equipment", "agricultural_equipment", "watercraft", "tires", "wheels"],
  category_submission_requirements: {
    cars: { top_level: ["make", "model", "year", "mileage_km", "fuel", "transmission", "drive"], category_details: [] },
    tires: { top_level: [], category_details: ["width_mm", "profile_percent", "diameter_in", "season"] },
    wheels: { top_level: [], category_details: ["diameter_in", "width_in", "bolt_holes", "pcd_mm"] }
  }
};

const fields = {
  seller_type: "private", make_mode: "catalog", model_mode: "catalog", make_id: "", model_id: "", manual_make: "", manual_model: "",
  generation_id: "", modification_id: "", body_type_id: "", body_variant_id: "", year: "", mileage_km: "", fuel: "", transmission: "", drive: "",
  engine_volume_l: "", power_hp: "", condition: "used", color: "", customs_status: "", technical_condition: "", body_condition: "",
  exchange: false, bargaining: false, credit: false, leasing: false, equipment: [], district: "", call_hours: "", damaged: false, parts_only: false,
  vin: "", description: "", price_amount: "100", currency: "BYN", region_id: "", city_mode: "catalog", city_id: "", manual_city: "", contact_phone: "", telegram_contact_url: "", viber_contact_url: ""
} as Parameters<typeof payloadFor>[0];

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.spyOn(api, "listingValidationPolicy").mockResolvedValue(policy);
  vi.spyOn(api, "listingOptions").mockResolvedValue({ colors: [], customs_statuses: [], technical_conditions: [], body_conditions: [], equipment: [] });
  vi.spyOn(api, "catalog").mockResolvedValue({ items: [] });
  vi.spyOn(api, "cities").mockResolvedValue({ items: [] });
  vi.spyOn(api, "photos").mockResolvedValue({ items: [] });
  vi.spyOn(api, "createDraft").mockResolvedValue({ listing: { id: "draft-1", slug: "draft-1", revision: 1 } as Listing });
  vi.spyOn(api, "updateDraft").mockImplementation(async (id, revision, payload) => ({
    listing: { id, slug: id, revision: revision + 1, ...(payload as Partial<Listing>) } as Listing
  }));
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("subcategory selling contract", () => {
  it("maps stable subtype slugs into the existing category_details object", () => {
    expect(payloadFor(fields, "motorcycles", "atv", { engine_volume_cc: "450", power_hp: "35" })).toMatchObject({
      category_code: "motorcycles",
      category_details: { category_code: "motorcycles", details: { vehicle_type: "atv", engine_volume_cc: 450, power_hp: 35 } }
    });
    expect(payloadFor(fields, "tires", "passenger", { width_mm: "205", profile_percent: "55", diameter_in: "16", season: "summer" }))
      .toMatchObject({ category_details: { category_code: "tires", details: { vehicle_type: "passenger", width_mm: 205, profile_percent: 55, diameter_in: 16, season: "summer" } } });
  });

  it("keeps older optional category details when editing without a recognized subtype", () => {
    expect(payloadFor(fields, "special_equipment", "", { equipment_type: "legacy crane type", weight_kg: "2500" }))
      .toMatchObject({ category_details: { category_code: "special_equipment", details: { equipment_type: "legacy crane type", weight_kg: 2500 } } });
  });

  it("preserves an unrecognized legacy subtype from an existing draft when it is saved", async () => {
    const listing = {
      id: "legacy-draft", slug: "legacy-draft", status: "draft", revision: 1,
      category_code: "special_equipment",
      category_details: { category_code: "special_equipment", details: { equipment_type: "legacy crane type", weight_kg: 2500 } },
      seller: { type: "private", id: "seller-1", name: "Продавец" }, photo_urls: [], description: "Описание", condition: "used"
    } as unknown as Listing;
    const updateDraft = vi.mocked(api.updateDraft);
    await act(async () => {
      root.render(createElement(SellForm, {
        initialListing: listing, makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
      await Promise.resolve();
    });
    const continuation = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Продолжить"));
    await act(async () => { continuation!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    const weightInput = [...container.querySelectorAll<HTMLLabelElement>("label")]
      .find((label) => label.querySelector("span")?.textContent?.startsWith("Масса, кг"))
      ?.querySelector<HTMLInputElement>("input");
    expect(weightInput).toBeTruthy();
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setter?.call(weightInput, "2600");
      weightInput!.dispatchEvent(new Event("input", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 800));
    });
    expect(updateDraft).toHaveBeenCalled();
    const savedPayload = updateDraft.mock.calls.at(-1)?.[2] as { category_details?: { details?: Record<string, unknown> } } | undefined;
    expect(savedPayload?.category_details?.details).toMatchObject({ equipment_type: "legacy crane type", weight_kg: 2600 });
  });

  it("requires tire dimensions without requiring car catalog or engine fields", async () => {
    await act(async () => {
      root.render(createElement(SellForm, {
        initialCategoryCode: "tires", initialSubcategory: "passenger", initialListing: null,
        makes: [], models: [], generations: [], bodyTypes: [], regions: [], cities: [], company: null
      }));
      await Promise.resolve();
    });
    const categorySelect = container.querySelector<HTMLSelectElement>('select[aria-label="Категория объявления"]');
    const subtypeSelect = container.querySelector<HTMLSelectElement>('select[aria-label="Подкатегория"]');
    expect(categorySelect?.value).toBe("tires");
    expect(subtypeSelect?.value).toBe("passenger");
    expect(container.querySelector('input[name="make_id"]')).toBeNull();
    expect(container.querySelector('input[name="year"]')).toBeNull();
    const continuation = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Продолжить"));
    expect(continuation).toBeTruthy();
    await act(async () => { continuation!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    const stepTwoContinuation = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Продолжить"));
    await act(async () => { stepTwoContinuation!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(container.textContent).toContain("ширину шины");
    expect(container.textContent).toContain("профиль шины");
    expect(container.textContent).toContain("сезон шин");
    expect(container.textContent).not.toContain("Выберите марку и модель");
  });
});
