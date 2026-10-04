import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListingCard } from "@/components/listing-card";
import { ListingDetail } from "@/components/listing-detail";
import { ModerationListingPreview } from "@/components/moderation-listing-preview";
import type { Listing } from "@/lib/types";

vi.mock("next/image", () => ({ default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ComponentProps<"img"> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} /> }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => undefined, refresh: () => undefined }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

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
});

const manualCityListing = {
  id: "listing-1",
  slug: "listing-1",
  title: "Марка Модель",
  make: { id: "make-1", slug: "make", name: "Марка" },
  model: { id: "model-1", slug: "model", name: "Модель" },
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "automatic",
  drive: "front",
  price: { amount: "10000", currency: "BYN" as const },
  region: { id: "region-1", slug: "minsk-region", name: "Минская область" },
  city: null,
  manual_city: "Заславль",
  seller: { type: "private" as const, id: "seller-1", name: "Продавец" },
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false,
  status: "draft" as const,
  revision: 1,
  description: "Описание",
  condition: "used",
  photo_urls: [],
  photos: []
} satisfies Listing;

describe("manual city display", () => {
  it("shows manual_city when the catalog city is absent", async () => {
    await act(async () => root.render(createElement("div", null,
      createElement(ListingCard, { listing: manualCityListing }),
      createElement(ListingDetail, { listing: manualCityListing }),
      createElement(ModerationListingPreview, { listing: manualCityListing })
    )));

    expect(container.querySelector(".listing-card .card-footer")?.textContent).toContain("Заславль");
    expect(container.querySelector(".location-line")?.textContent).toContain("Заславль, Минская область");
    expect(container.querySelector(".seller-box")?.textContent).toContain("Заславль, Минская область");
    expect(container.querySelector(".moderation-preview")?.textContent).toContain("Заславль, Минская область");
    expect(container.textContent).not.toContain("undefined");
  });
});
