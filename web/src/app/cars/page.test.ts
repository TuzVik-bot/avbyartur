import { describe, expect, it } from "vitest";
import { generateMetadata } from "./page";

describe("cars search canonical", () => {
  it("preserves page and supported filters while dropping tracking parameters", async () => {
    const metadata = await generateMetadata({
      searchParams: Promise.resolve({ page: "2", sort: "newest", make_id: "make-1", utm_source: "newsletter" })
    });

    expect(metadata.alternates?.canonical).toBe(
      "https://suite-s1.denjik.by/cars?make_id=make-1&page=2&sort=newest"
    );
  });

  it("normalizes repeated filters to their first value", async () => {
    const metadata = await generateMetadata({ searchParams: Promise.resolve({ q: ["BMW", "ignored"] }) });

    expect(metadata.alternates?.canonical).toBe("https://suite-s1.denjik.by/cars?q=BMW");
  });
});

it("keeps the passenger-car route despite a foreign category query", async () => {
 const metadata = await generateMetadata({ searchParams: Promise.resolve({ category_code: "tires", season: "winter", condition: "used" }) });
 expect(metadata.alternates?.canonical).toBe("https://suite-s1.denjik.by/cars?condition=used");
});
