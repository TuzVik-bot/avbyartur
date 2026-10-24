import { apiRequest } from "@/lib/api";
import type { Listing } from "@/lib/types";

export async function fetchComparisonListings(ids: string[]): Promise<{ items: Listing[] }> {
  if (ids.length < 1 || ids.length > 4) {
    throw new RangeError("Comparison accepts between one and four listing IDs");
  }

  const params = new URLSearchParams();
  for (const id of ids) params.append("ids", id);
  return apiRequest<{ items: Listing[] }>(`listings/compare?${params.toString()}`);
}
