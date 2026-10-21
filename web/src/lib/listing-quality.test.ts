import { describe, expect, it } from "vitest";
import { buildListingQuality, type ListingQualityInput } from "@/lib/listing-quality";

const baseInput: ListingQualityInput = {
  categoryCode: "cars",
  requirements: { top_level: ["make", "model", "year", "mileage_km", "fuel", "transmission", "drive"], category_details: [] },
  values: {
    title: "Volvo V60 2020",
    make: "Volvo",
    model: "V60",
    year: "2020",
    mileage_km: "50000",
    fuel: "diesel",
    transmission: "automatic",
    drive: "front",
    condition: "used",
    description: "После обслуживания",
    price: "10000",
    region: "region-1",
    city: "city-1",
    contact_phone: "present",
    engine_volume_l: "",
    power_hp: "",
    vin: ""
  },
  targets: {
    year: { step: 2, fieldId: "year" },
    mileage_km: { step: 2, fieldId: "mileage_km" },
    engine_volume_l: { step: 2, fieldId: "engine_volume_l" },
    vin: { step: 3, fieldId: "vin" }
  },
  readyPhotoCount: 2,
  minimumPhotoCount: 1
};

describe("listing quality helper", () => {
  it("summarizes current car requirements and keeps optional details separate", () => {
    const quality = buildListingQuality(baseInput);

    expect(quality.required.every((check) => check.status === "complete")).toBe(true);
    expect(quality.recommended.map(({ id, status }) => [id, status])).toEqual([
      ["engine_volume_l", "missing"],
      ["power_hp", "missing"],
      ["vin", "missing"]
    ]);
    expect(quality.recommended[0]?.target).toEqual({ step: 2, fieldId: "engine_volume_l" });
    expect(quality.recommended[2]?.target).toEqual({ step: 3, fieldId: "vin" });
    expect(quality.photoAdvice.join(" ")).toContain("обоих боков");
  });

  it("uses category policy for required checks without applying car-only requirements to motorcycles", () => {
    const quality = buildListingQuality({
      ...baseInput,
      categoryCode: "motorcycles",
      requirements: { top_level: ["make", "model", "year"], category_details: ["vehicle_type"] },
      values: { ...baseInput.values, mileage_km: "", fuel: "", transmission: "", drive: "" }
    });

    const identity = quality.required.find((check) => check.id === "identity");
    const categoryDetails = quality.required.find((check) => check.id === "category-details");
    expect(identity?.status).toBe("complete");
    expect(categoryDetails?.status).toBe("not_checked");
    expect(categoryDetails?.detail).toContain("тип техники");
    expect(categoryDetails?.detail).toContain("не проверяет и не редактирует");
    expect(quality.required.some((check) => check.detail.includes("пробег"))).toBe(false);
    expect(quality.recommended).toHaveLength(0);
    expect(quality.photoAdvice.join(" ")).toContain("мотоцикл целиком");
  });

  it("offers category-specific watercraft photo guidance without marking any angle as verified", () => {
    const quality = buildListingQuality({ ...baseInput, categoryCode: "watercraft" });

    expect(quality.photoAdvice.join(" ")).toContain("палубу");
    expect(quality.photoAdvice.join(" ")).toContain("двигатель");
    expect(quality.photoAdvice.some((tip) => tip.toLowerCase().includes("проверено"))).toBe(false);
  });

  it("shows missing required fields with a direct edit target and treats unknown photo policy as unverified", () => {
    const quality = buildListingQuality({
      ...baseInput,
      values: { ...baseInput.values, title: "", year: "", description: "", region: "" },
      minimumPhotoCount: null,
      readyPhotoCount: 0,
      targets: { ...baseInput.targets, make: { step: 2, fieldId: "make_id" }, description: { step: 3, fieldId: "description" }, region: { step: 4, fieldId: "region_id" }, photos: { step: 5, fieldId: "photos" } }
    });

    const identity = quality.required.find((check) => check.id === "identity");
    expect(identity?.status).toBe("missing");
    expect(identity?.detail).toContain("год выпуска");
    expect(identity?.target).toEqual({ step: 2, fieldId: "make_id" });
    expect(quality.required.find((check) => check.id === "description")?.target).toEqual({ step: 3, fieldId: "description" });
    expect(quality.required.find((check) => check.id === "photos")?.status).toBe("not_checked");
  });
});
