import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dealerTeamApi, type DealerFeed, type DealerFeedImportRun, type DealerFeedMissingCandidate, type DealerTeamMember } from "@/lib/dealer";
import { DealerFeeds } from "@/components/dealer-feeds";

const owner: DealerTeamMember = {
  id: "owner-row", user_id: "owner-user", email: "owner@example.test", display_name: "Владелец",
  role: "owner", status: "active", revision: 1, created_at: "2026-10-01T10:00:00Z"
};
const feed: DealerFeed = {
  id: "feed-1", name: "Каталог", format: "csv", status: "active", field_mapping: {}, api_token_prefix: null,
  manual_conflict_policy: "review", missing_retirement_enabled: false, missing_retirement_delay_hours: 168,
  created_at: "2026-10-01T10:00:00Z"
};
const candidate: DealerFeedMissingCandidate = {
  dealer_external_id: "STOCK-100", listing_id: "listing-1", title: "Toyota Camry", status: "active",
  listing_revision: 4, expected_listing_revision: 4, snapshot_digest: "a".repeat(64),
  missing_since: "2026-09-30T10:00:00Z", due_at: "2026-09-30T11:00:00Z", eligible: true, reason: null
};
const run = (dry_run: boolean): DealerFeedImportRun => ({
  id: dry_run ? "preview-run" : "applied-run", feed_id: feed.id, status: dry_run ? "preview" : "succeeded", dry_run,
  source_filename: "stock.csv", total_rows: 1, applied_rows: dry_run ? 0 : 1, rejected_rows: 0,
  error_code: null, created_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-01T10:00:01Z"
});

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
  vi.restoreAllMocks();
});

async function render() {
  await act(async () => {
    root.render(createElement(DealerFeeds, { initialFeeds: [feed], initialTeam: [owner], currentUserId: owner.user_id }));
  });
}

describe("dealer feeds", () => {
  it("runs a preview and an apply with separate idempotency keys and displays history", async () => {
    await render();
    const importCall = vi.spyOn(dealerTeamApi, "importFeedFile")
      .mockResolvedValueOnce({ run: run(true), missing_candidates: [] })
      .mockResolvedValueOnce({ run: run(false), missing_candidates: [] });
    vi.spyOn(dealerTeamApi, "importRun").mockImplementation(async (id) => ({ run: run(id === "preview-run") }));
    vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: [] });
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["id,make\n1,Toyota"], "stock.csv", { type: "text/csv" });
    Object.defineProperty(fileInput, "files", { configurable: true, value: [file] });
    await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
    const buttons = [...container.querySelectorAll<HTMLButtonElement>(".feed-import-actions button")];
    await act(async () => { buttons[0].click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    await act(async () => { buttons[1].click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(importCall).toHaveBeenNthCalledWith(1, feed.id, file, true, expect.any(String), false);
    expect(importCall).toHaveBeenNthCalledWith(2, feed.id, file, false, expect.any(String), false);
    expect(importCall.mock.calls[0][3]).not.toBe(importCall.mock.calls[1][3]);
    expect(container.textContent).toContain("применён");
    expect(container.textContent).toContain("История импортов");
  });

  it("does not expose file import or creation to viewers", async () => {
    await act(async () => {
      root.render(createElement(DealerFeeds, {
        initialFeeds: [feed], initialTeam: [{ ...owner, role: "viewer", user_id: "viewer-user" }], currentUserId: "viewer-user"
      }));
    });
    expect(container.querySelector(".dealer-feed-create")).toBeNull();
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.textContent).toContain("доступен просмотр");
  });

  it("lets sellers import and read candidates without feed management or pause confirmation", async () => {
    await act(async () => {
      root.render(createElement(DealerFeeds, {
        initialFeeds: [feed], initialTeam: [{ ...owner, role: "seller", user_id: "seller-user" }], currentUserId: "seller-user"
      }));
    });
    vi.spyOn(dealerTeamApi, "missingCandidates").mockResolvedValue({ items: [candidate] });
    expect(container.querySelector(".dealer-feed-create")).toBeNull();
    expect(container.querySelector(".feed-policy")).toBeNull();
    expect(container.querySelector('input[type="file"]')).not.toBeNull();
    await act(async () => { container.querySelector<HTMLButtonElement>(".feed-candidates button")!.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).toContain("STOCK-100");
    expect(container.textContent).not.toContain("Подтвердить паузу");
  });

  it("saves feed policy, previews complete snapshots, and confirms an eligible candidate", async () => {
    await render();
    const policyCall = vi.spyOn(dealerTeamApi, "updateFeedPolicy").mockResolvedValue({
      feed: { ...feed, manual_conflict_policy: "feed_wins", missing_retirement_enabled: true, missing_retirement_delay_hours: 24 },
      api_token: null
    });
    const snapshotPreview = vi.spyOn(dealerTeamApi, "importFeedFile").mockResolvedValue({ run: run(true), missing_candidates: [candidate] });
    vi.spyOn(dealerTeamApi, "importRun").mockResolvedValue({ run: run(true) });
    vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: [] });
    vi.spyOn(dealerTeamApi, "missingCandidates").mockResolvedValue({ items: [candidate] });
    const confirmationCall = vi.spyOn(dealerTeamApi, "confirmMissingCandidate").mockResolvedValue({ run: run(false), paused_external_ids: [candidate.dealer_external_id] });

    const selects = container.querySelectorAll<HTMLSelectElement>(".feed-policy select");
    await act(async () => {
      selects[0].value = "feed_wins";
      selects[0].dispatchEvent(new Event("change", { bubbles: true }));
    });
    const delayInput = container.querySelector<HTMLInputElement>(".feed-policy input[type='number']")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setInputValue?.call(delayInput, "24");
      delayInput.dispatchEvent(new Event("input", { bubbles: true }));
      delayInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const retirementToggle = container.querySelector<HTMLInputElement>(".feed-policy input[type='checkbox']")!;
    await act(async () => { retirementToggle.click(); });
    await act(async () => { container.querySelector<HTMLButtonElement>(".feed-policy button")!.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(policyCall).toHaveBeenCalledWith(feed.id, {
      manual_conflict_policy: "feed_wins", missing_retirement_enabled: true, missing_retirement_delay_hours: 24
    });

    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["dealer_external_id,title\nSTOCK-100,Toyota Camry"], "stock.csv", { type: "text/csv" });
    Object.defineProperty(fileInput, "files", { configurable: true, value: [file] });
    await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
    const snapshotToggle = [...container.querySelectorAll<HTMLInputElement>(".feed-file-import input[type='checkbox']")][0];
    await act(async () => { snapshotToggle.click(); });
    const previewButton = [...container.querySelectorAll<HTMLButtonElement>(".feed-import-actions button")][0];
    await act(async () => { previewButton.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(snapshotPreview).toHaveBeenCalledWith(feed.id, file, true, expect.any(String), true);
    expect(container.textContent).toContain("Предпросмотр отсутствующих объявлений");
    expect(container.querySelector('a[href="/api/v1/dealer/feeds/samples/schema"]')).not.toBeNull();

    const checkCandidates = [...container.querySelectorAll<HTMLButtonElement>(".feed-candidates button")].find((button) => button.textContent?.includes("Проверить список"))!;
    await act(async () => { checkCandidates.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    const confirmButton = [...container.querySelectorAll<HTMLButtonElement>(".feed-candidates button")].find((button) => button.textContent?.includes("Подтвердить паузу"))!;
    await act(async () => { confirmButton.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(confirmationCall).toHaveBeenCalledWith(feed.id, {
      dealer_external_id: candidate.dealer_external_id,
      expected_listing_revision: candidate.expected_listing_revision,
      snapshot_digest: candidate.snapshot_digest
    }, expect.any(String));
  });
});
