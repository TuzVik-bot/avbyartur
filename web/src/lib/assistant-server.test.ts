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
});
