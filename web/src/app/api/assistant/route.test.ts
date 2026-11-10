import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const answer = vi.fn();
vi.mock("@/lib/assistant-server", () => ({ answerAssistant: answer, assistantModelEnabled: () => false }));
// A fresh module per test resets the in-memory rate limits and budget.
async function loadPost() {
  vi.resetModules();
  return (await import("./route")).POST;
}
const okReply = { text: "ok", filters: {}, listings: [], links: [], labels: [], engine: "basic" };
beforeEach(() => { answer.mockReset(); answer.mockResolvedValue(okReply); });
afterEach(() => { vi.unstubAllEnvs(); });
function request(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://suite-s1.denjik.by/api/assistant", { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
}
type Reserve = { reserveModelCall: () => boolean };

describe("assistant endpoint", () => {
  it("blocks cross-site calls", async () => {
    const POST = await loadPost();
    expect((await POST(request({ message: "hi" }, { Origin: "https://evil.example" }))).status).toBe(403);
    expect(answer).not.toHaveBeenCalled();
  });
  it("bounds the body and message", async () => {
    const POST = await loadPost();
    expect((await POST(request({ message: "a".repeat(22000) }))).status).toBe(413);
    expect((await POST(request({ message: "a".repeat(1201) }))).status).toBe(400);
  });
  it("strips private pages and unsafe search keys", async () => {
    const POST = await loadPost();
    expect((await POST(request({ message: "найди", page: { path: "/account", title: "private", text: "secret" }, filters: { status: "draft", currency: "USD" } }))).status).toBe(200);
    expect(answer.mock.calls[0][0]).toMatchObject({ page: undefined, filters: { currency: "USD" } });
  });
});

describe("assistant rate limits", () => {
  it("allows ten requests per IP per hour and answers the eleventh with a Russian 429", async () => {
    const POST = await loadPost();
    for (let index = 0; index < 10; index++) expect((await POST(request({ message: "найди" }, { "x-real-ip": "10.0.0.1" }))).status).toBe(200);
    const limited = await POST(request({ message: "найди" }, { "x-real-ip": "10.0.0.1" }));
    expect(limited.status).toBe(429);
    expect((await limited.json()).message).toMatch(/Попробуйте/);
    expect(Number(limited.headers.get("Retry-After"))).toBeGreaterThan(0);
    expect((await POST(request({ message: "найди" }, { "x-real-ip": "10.0.0.2" }))).status).toBe(200);
  });
  it("caps one IP at thirty requests per day across hours", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      const POST = await loadPost();
      let accepted = 0;
      for (let hour = 0; hour < 4; hour++) {
        vi.setSystemTime(new Date(Date.UTC(2026, 10, 9, hour, 0, 0)));
        for (let index = 0; index < 10; index++) if ((await POST(request({ message: "найди" }, { "x-real-ip": "10.0.0.3" }))).status === 200) accepted++;
      }
      expect(accepted).toBe(30);
    } finally { vi.useRealTimers(); }
  });
  it("counts only reserved model calls against the daily budget and then degrades instead of rejecting", async () => {
    vi.stubEnv("ASSISTANT_DAILY_MODEL_BUDGET", "2");
    const reservations: boolean[] = [];
    answer.mockImplementation(async (input: Reserve & { message: string }) => {
      if (input.message !== "без модели") reservations.push(input.reserveModelCall());
      return okReply;
    });
    const POST = await loadPost();
    expect((await POST(request({ message: "без модели" }, { "x-real-ip": "10.0.1.1" }))).status).toBe(200);
    for (let index = 0; index < 3; index++) expect((await POST(request({ message: "найди" }, { "x-real-ip": `10.0.1.${index + 2}` }))).status).toBe(200);
    expect(reservations).toEqual([true, true, false]);
  });
  it("falls back to the default daily budget for an invalid value", async () => {
    vi.stubEnv("ASSISTANT_DAILY_MODEL_BUDGET", "lots");
    const reservations: boolean[] = [];
    answer.mockImplementation(async (input: Reserve) => { reservations.push(input.reserveModelCall()); return okReply; });
    const POST = await loadPost();
    for (let index = 0; index < 46; index++) await POST(request({ message: "найди" }, { "x-real-ip": `10.0.2.${index}` }));
    expect(reservations.filter(Boolean)).toHaveLength(45);
  });
  it("returns 503 only for non-model failures", async () => {
    answer.mockRejectedValue(new Error("catalog_unavailable"));
    const POST = await loadPost();
    const response = await POST(request({ message: "найди" }));
    expect(response.status).toBe(503);
    expect((await response.json()).message).toContain("Не удалось получить данные сайта");
  });
});
