import { describe, expect, it } from "vitest";
import { generateMetadata } from "./page";

describe("cars search canonical", () => {
  it.each([
    { condition: "used" }, { fuel: "electric" }, { page: "2" },
    { sort: "newest" }, { page: "1", condition: "used" },
    { page: ["1", "2"] }, { unknown: "value" },
  ])("noindexes query variants %j while following their links", async (params) => {
    const metadata = await generateMetadata({ searchParams: Promise.resolve(params) });
    expect(metadata.robots).toMatchObject({ index: false, follow: true, googleBot: { index: false, follow: true } });
  });

  it.each([{}, { page: "1" }])("keeps the clean catalog canonical for %j", async (params) => {
    const metadata = await generateMetadata({ searchParams: Promise.resolve(params) });
    expect(metadata.robots).toBeUndefined();
    expect(metadata.alternates?.canonical).toBe("https://xn--80aeylebmo7f.xn--90ais/cars");
  });
  it("preserves page and supported filters while dropping tracking parameters", async () => {
    const metadata = await generateMetadata({
      searchParams: Promise.resolve({ page: "2", sort: "newest", make_id: "make-1", utm_source: "newsletter" })
    });

    expect(metadata.alternates?.canonical).toBe(
      "https://xn--80aeylebmo7f.xn--90ais/cars?make_id=make-1&page=2&sort=newest"
    );
  });

  it("normalizes repeated filters to their first value", async () => {
    const metadata = await generateMetadata({ searchParams: Promise.resolve({ q: ["BMW", "ignored"] }) });

    expect(metadata.alternates?.canonical).toBe("https://xn--80aeylebmo7f.xn--90ais/cars?q=BMW");
  });
});
