import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ListingPhotoBadgeEditor } from "@/components/listing-photo-badge-editor";
import { api } from "@/lib/api";
import type { Listing } from "@/lib/types";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const listing = { id: "listing-1", revision: 2, photo_badges: ["verified"] } as Listing;
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); refresh.mockReset(); });

it("saves selected labels and uses the returned revision for the next save", async () => {
  const save = vi.spyOn(api, "setListingPhotoBadges").mockResolvedValue({ listing: { ...listing, revision: 3, photo_badges: ["verified", "free_history"] } });
  act(() => root.render(<ListingPhotoBadgeEditor listing={listing} />));
  expect(container.querySelectorAll('input[type="checkbox"]')).toHaveLength(3);
  expect(container.querySelector<HTMLInputElement>("input")?.checked).toBe(true);
  act(() => container.querySelectorAll<HTMLInputElement>("input")[1].click());
  await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
  expect(save).toHaveBeenCalledWith("listing-1", 2, ["verified", "free_history"]);
  expect(container.querySelector('[role="status"]')?.textContent).toBe("Метки сохранены");
  expect(refresh).toHaveBeenCalledOnce();
  await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
  expect(save).toHaveBeenLastCalledWith("listing-1", 3, ["verified", "free_history"]);
});

it("reports failures and synchronizes refreshed listing values", async () => {
  vi.spyOn(api, "setListingPhotoBadges").mockRejectedValue(new Error("Версия объявления изменилась"));
  act(() => root.render(<ListingPhotoBadgeEditor listing={listing} />));
  await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("Версия объявления");
  expect(refresh).not.toHaveBeenCalled();
  act(() => root.render(<ListingPhotoBadgeEditor listing={{ ...listing, revision: 4, photo_badges: [] }} />));
  expect(container.querySelector<HTMLInputElement>("input")?.checked).toBe(false);
});
