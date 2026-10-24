import { afterEach, describe, expect, it, vi } from "vitest";
import { answerAssistant } from "@/lib/assistant-server";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
const input = { message: "машина до 10 тысяч долларов", filters: {}, history: [] };
function mockApi(total = 0) {
  const fetch = vi.fn(async (url: string) => {
    if (url.includes("chat/completions")) return Response.json({ choices: [{ message: { content: JSON.stringify({ intent: "search", filters: { category_code: "cars", price_max: "10000", currency: "USD" }, text: "" }) } }] });
    if (url.includes("/listings?")) return Response.json({ items: [], pagination: { total } });
    return Response.json({ items: [] });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
describe("assistant server", () => {
  it("offers only verified nearby searches and preserves the original requirements", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = vi.fn(async (url: string) => {
      const params = new URL(url).searchParams;
      return Response.json(url.includes("/listings?")
        ? { items: [], pagination: { total: params.get("price_max") === "11000" ? 2 : 0 } }
        : { items: [] });
    });
    vi.stubGlobal("fetch", fetch);
    const filters = { price_max: "10000", currency: "BYN", year_min: "2018", city_id: "minsk", damaged: "false", parts_only: "false" };
    const reply = await answerAssistant({ message: "Покажи машины", filters, history: [] });
    expect(reply.filters).toMatchObject(filters);
    expect(reply.total).toBe(0);
    expect(reply.links).toHaveLength(1);
    expect(reply.links[0].title).toContain("1 000 BYN");
    const suggestion = new URL(reply.links[0].href, "https://example.test");
    expect(suggestion.searchParams.get("price_max")).toBe("11000");
    expect(suggestion.searchParams.get("price_min")).toBe("10000.01");
    expect(suggestion.searchParams.get("damaged")).toBe("false");
    expect(suggestion.searchParams.get("city_id")).toBe("minsk");
    expect(reply.text).toContain("Похоже на ваш запрос");
    expect(reply.text).toContain("Выберите ссылку ниже");
  });
  it("keeps exact matches when a nearby search fails", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    let searches = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (!url.includes("/listings?")) return Response.json({ items: [] });
      if (++searches > 1) throw new Error("unavailable");
      return Response.json({ items: [], pagination: { total: 0 } });
    }));
    const reply = await answerAssistant(input);
    expect(reply.total).toBe(0);
    expect(reply.links).toEqual([]);
  });
  it("offers a year or city alternative independently without changing vehicle requirements", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const params = new URL(url).searchParams;
      const alternative = params.get("year_min") === "2017" || !params.has("city_id");
      return Response.json(url.includes("/listings?")
        ? { items: [], pagination: { total: alternative ? 1 : 0 } }
        : { items: [] });
    }));
    const reply = await answerAssistant({ message: "Покажи машины", filters: { year_min: "2018", city_id: "minsk", fuel: "diesel", transmission: "automatic" }, history: [] });
    expect(reply.links).toHaveLength(2);
    const year = new URL(reply.links[0].href, "https://example.test").searchParams;
    expect(year.get("year_min")).toBe("2017");
    expect(year.get("year_max")).toBe("2017");
    expect(reply.links[0].title).toContain("только 2017");
    expect(year.get("city_id")).toBe("minsk");
    const city = new URL(reply.links[1].href, "https://example.test").searchParams;
    expect(city.has("city_id")).toBe(false);
    expect(city.get("year_min")).toBe("2018");
    for (const params of [year, city]) {
      expect(params.get("fuel")).toBe("diesel");
      expect(params.get("transmission")).toBe("automatic");
    }
  });
  it("applies a relative budget increase in basic mode and keeps other filters", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = vi.fn(async (url: string) => {
      if (url.includes("/listings?")) {
        const params = new URL(url).searchParams;
        expect(params.get("price_min")).toBe("10000.01");
        expect(params.get("price_max")).toBe("11000");
        expect(params.get("transmission")).toBe("automatic");
        return Response.json({ items: [], pagination: { total: 1 } });
      }
      return Response.json({ items: [] });
    });
    vi.stubGlobal("fetch", fetch);
    const reply = await answerAssistant({
      message: "Да, покажи на 1000 рублей дороже",
      filters: { price_max: "10000", currency: "BYN", transmission: "automatic" },
      history: []
    });
    expect(reply.total).toBe(1);
    expect(reply.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN", transmission: "automatic" });
  });
  it("applies the bounded default step to a qualitative budget increase", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = vi.fn(async (url: string) => {
      if (!url.includes("/listings?")) return Response.json({ items: [] });
      const params = new URL(url).searchParams;
      expect(params.get("price_min")).toBe("10000.01");
      expect(params.get("price_max")).toBe("11000");
      expect(params.get("currency")).toBe("BYN");
      return Response.json({ items: [], pagination: { total: 0 } });
    });
    vi.stubGlobal("fetch", fetch);
    const reply = await answerAssistant({ message: "Давай немного дороже", filters: { price_max: "10000", currency: "BYN" }, history: [] });
    expect(reply.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN" });
    expect(reply.text).toContain("Бюджет увеличен: теперь от");
    expect(reply.text.replace(/\s/g, "")).toContain("до11000BYN");
  });
  it("keeps a relative budget increase and prior filters in the AI search plan", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "test-not-a-real-key");
    vi.stubEnv("ASSISTANT_BASE_URL", "https://openrouter.ai/api/v1");
    vi.stubEnv("ASSISTANT_MODEL", "dots-studio/dots-3-note-preview:free");
    const fetch = vi.fn(async (url: string) => {
      if (url.includes("chat/completions")) return Response.json({ choices: [{ message: { content: JSON.stringify({
        intent: "search", filters: { category_code: "cars", price_max: "1000", currency: "BYN" }, text: ""
      }) } }] });
      if (url.includes("/listings?")) {
        const params = new URL(url).searchParams;
        expect(params.get("price_min")).toBe("10000.01");
        expect(params.get("price_max")).toBe("11000");
        expect(params.get("transmission")).toBe("automatic");
        return Response.json({ items: [], pagination: { total: 1 } });
      }
      return Response.json({ items: [] });
    });
    vi.stubGlobal("fetch", fetch);
    const reply = await answerAssistant({
      message: "Да, покажи на 1000 рублей дороже",
      filters: { price_max: "10000", currency: "BYN", transmission: "automatic" },
      history: []
    });
    expect(reply.engine).toBe("ai");
    expect(reply.total).toBe(1);
    expect(reply.filters).toMatchObject({ price_min: "10000.01", price_max: "11000", currency: "BYN", transmission: "automatic" });
  });
  it("does not suggest relaxing a successful search", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = mockApi(1);
    const reply = await answerAssistant(input);
    expect(reply.links).toEqual([]);
    expect(fetch.mock.calls.filter(([url]) => url.includes("/listings?"))).toHaveLength(1);
  });
  it("uses live public search without cookies and handles no matches", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = mockApi();
    const reply = await answerAssistant(input);
    expect(reply.total).toBe(0);
    expect(reply.text).toContain("сейчас нет");
    expect(reply.searchHref).toContain("price_max=10000");
    const call = fetch.mock.calls.find(([url]) => url.includes("/listings?"));
    expect(call?.[0]).toContain("currency=USD");
    expect(reply.engine).toBe("basic");
  });
  it("does not search until currency has been specified", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "");
    const fetch = mockApi();
    const reply = await answerAssistant({ ...input, message: "до 10 тысяч" });
    expect(reply.text).toContain("USD");
    expect(fetch.mock.calls.some(([url]) => url.includes("/listings?"))).toBe(false);
  });
  it("allows only free OpenRouter models and disables provider fallback", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "test-not-a-real-key");
    vi.stubEnv("ASSISTANT_BASE_URL", "https://openrouter.ai/api/v1");
    vi.stubEnv("ASSISTANT_MODEL", "google/gemma-4-31b-it:free");
    const fetch = mockApi(3);
    const reply = await answerAssistant(input);
    expect(reply.engine).toBe("ai");
    expect(reply.total).toBe(3);
    const call = fetch.mock.calls.find(([url]) => url.includes("chat/completions"));
    expect(call).toBeDefined();
    vi.stubEnv("ASSISTANT_MODEL", "openai/gpt-4.1-mini");
    await expect(answerAssistant(input)).rejects.toThrow("model_configuration");
  });
  it("keeps a comparison answer instead of treating the word variants as a new search", async () => {
    vi.stubEnv("ASSISTANT_API_KEY", "test-not-a-real-key");
    vi.stubEnv("ASSISTANT_BASE_URL", "https://openrouter.ai/api/v1");
    vi.stubEnv("ASSISTANT_MODEL", "dots-studio/dots-3-note-preview:free");
    const fetch = vi.fn(async (url: string) => url.includes("chat/completions")
      ? Response.json({ choices: [{ message: { content: JSON.stringify({ intent: "answer", text: "Первый вариант новее.", filters: {} }) } }] })
      : Response.json({ items: [] }));
    vi.stubGlobal("fetch", fetch);
    const reply = await answerAssistant({ ...input, message: "Сравни первые три варианта" });
    expect(reply.text).toBe("Первый вариант новее.");
    expect(fetch.mock.calls.some(([url]) => url.includes("/listings?"))).toBe(false);
  });
  it("compares selected listings using fresh public facts", async () => {
    const fetch = vi.fn(async () => Response.json({ listing: { id: "id-1", slug: "car", title: "[ТЕСТ] Машина", make: null, model: null, price: { amount: "10000", currency: "BYN" }, year: 2020, mileage_km: 150000, fuel: "petrol", transmission: "automatic", drive: "front" } }));
    vi.stubGlobal("fetch", fetch);
    const reply = await answerAssistant({ ...input, message: "Сравни первые три", listingIds: ["id-1"] });
    expect(reply.text).toContain("[ТЕСТ] Машина");
    expect(reply.text).toContain("2020");
    expect(reply.links).toHaveLength(1);
    expect(fetch.mock.calls).toHaveLength(1);
  });
});
