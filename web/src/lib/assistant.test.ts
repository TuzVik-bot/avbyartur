import { describe, expect, it } from "vitest";
import { isPublicAssistantPage, parseAssistantSearch, validateAssistantFilters } from "@/lib/assistant";

const catalog = { makes: [{ id: "bmw", name: "BMW", slug: "bmw", aliases: ["БМВ"] }], models: [{ id: "x5", name: "X5", slug: "x5", make_id: "bmw" }], cities: [{ id: "minsk", name: "Минск", slug: "minsk" }] };
describe("assistant search", () => {
  it("clarifies unspecified currency and retains budget in follow-up", () => {
    const first = parseAssistantSearch("Найди мне тачку бюджет до 10 тысяч", {}, catalog);
    expect(first.filters.price_max).toBe("10000");
    expect(first.needsCurrency).toBe(true);
    const next = parseAssistantSearch("В долларах, автомат, только в Минске и не старше 2015 года", first.filters, catalog);
    expect(next.filters).toMatchObject({ price_max: "10000", currency: "USD", transmission: "automatic", city_id: "minsk", year_min: "2015" });
    expect(next.needsCurrency).toBe(false);
  });
  it("treats a more-expensive follow-up as an increment to the active budget", () => {
    const result = parseAssistantSearch("Да, покажи на 1000 рублей дороже", { price_max: "10000", currency: "BYN", transmission: "automatic" }, catalog);
    expect(result.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN", transmission: "automatic" });
    expect(result.relativeBudgetIncrease).toMatchObject({ applied: true, currency: "BYN" });
    expect(result.needsCurrency).toBe(false);
  });
  it("uses a currency stated with the increase when the original budget was still unconfirmed", () => {
    const result = parseAssistantSearch("Покажи на 1000 рублей дороже", { price_max: "10000" }, catalog);
    expect(result.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN" });
    expect(result.relativeBudgetIncrease).toMatchObject({ applied: true, currency: "BYN" });
  });
  it("uses the same modest increase for a qualitative request to go a little higher", () => {
    const result = parseAssistantSearch("Давай немного дороже", { price_max: "10000", currency: "BYN" }, catalog);
    expect(result.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN" });
    expect(result.relativeBudgetIncrease).toMatchObject({ applied: true, qualitative: true });
  });
  it("does not change the budget currency when the relative increase conflicts with it", () => {
    const result = parseAssistantSearch("Покажи на 1000 рублей дороже", { price_max: "10000", currency: "USD" }, catalog);
    expect(result.filters).toMatchObject({ price_max: "10000", currency: "USD" });
    expect(result.relativeBudgetIncrease).toMatchObject({ applied: false, currencyConflict: true });
  });
  it("keeps the active USD budget when a qualitative increase explicitly requests BYN", () => {
    const result = parseAssistantSearch("Покажи немного дороже в BYN", { price_max: "10000", currency: "USD" }, catalog);
    expect(result.filters).toMatchObject({ price_max: "10000", currency: "USD" });
    expect(result.filters.price_min).toBeUndefined();
    expect(result.relativeBudgetIncrease).toMatchObject({ amount: 1000, currency: "BYN", applied: false, currencyConflict: true });
  });
  it("applies a stated trailing currency to an unconfirmed relative increase", () => {
    const result = parseAssistantSearch("Покажи на 1000 дороже в долларах", { price_max: "10000" }, catalog);
    expect(result.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "USD" });
    expect(result.relativeBudgetIncrease).toMatchObject({ applied: true, currency: "USD", currencyConflict: false });
  });
  it("matches catalog aliases and models and distinguishes mileage/year from budget", () => {
    const result = parseAssistantSearch("БМВ X5 дизель пробег до 150 тысяч км от 2018 года", {}, catalog);
    expect(result.filters).toMatchObject({ make_id: "bmw", model_id: "x5", fuel: "diesel", mileage_max: "150000", year_min: "2018" });
    expect(result.filters.price_max).toBeUndefined();
  });
  it("resets and explicitly removes constraints", () => {
    expect(parseAssistantSearch("начнем заново", { price_max: "10000", currency: "USD" }, catalog).filters).toEqual({ category_code: "cars" });
    expect(parseAssistantSearch("любой город, любая коробка", { city_id: "minsk", transmission: "automatic" }, catalog).filters.transmission).toBeUndefined();
  });
  it("rejects arbitrary keys, unsafe identifiers and invalid enums", () => {
    expect(validateAssistantFilters({ currency: "EUR", make_id: "../../admin", status: "draft", page_size: "1000", price_max: -1, year_min: 1700, transmission: "automatic" })).toEqual({ transmission: "automatic" });
  });
  it("excludes private and form pages from summarization", () => {
    for (const path of ["/account", "/admin", "/login", "/sell", "/api/v1/me", "//evil.example", "/cars/../../account"]) expect(isPublicAssistantPage(path)).toBe(false);
    expect(isPublicAssistantPage("/cars/bmw/x5/abc-123")).toBe(true);
    expect(isPublicAssistantPage("/customs-calculator")).toBe(true);
  });
});
