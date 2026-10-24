import { beforeEach, describe, expect, it, vi } from "vitest";
const answer = vi.fn();
vi.mock("@/lib/assistant-server", () => ({ answerAssistant: answer, assistantModelEnabled: () => false }));
const { POST } = await import("./route");
beforeEach(() => { answer.mockReset(); answer.mockResolvedValue({ text: "ok", filters: {}, listings: [], links: [], labels: [], engine: "basic" }); });
function request(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://suite-s1.denjik.by/api/assistant", { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
}
describe("assistant endpoint", () => {
  it("blocks cross-site calls", async () => {
    expect((await POST(request({ message: "hi" }, { Origin: "https://evil.example" }))).status).toBe(403);
    expect(answer).not.toHaveBeenCalled();
  });
  it("bounds the body and message", async () => {
    expect((await POST(request({ message: "a".repeat(22000) }))).status).toBe(413);
    expect((await POST(request({ message: "a".repeat(1201) }))).status).toBe(400);
  });
  it("strips private pages and unsafe search keys", async () => {
    expect((await POST(request({ message: "найди", page: { path: "/account", title: "private", text: "secret" }, filters: { status: "draft", currency: "USD" } }))).status).toBe(200);
    expect(answer.mock.calls[0][0]).toMatchObject({ page: undefined, filters: { currency: "USD" } });
  });
});
