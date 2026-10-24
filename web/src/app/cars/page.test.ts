import { describe, expect, it } from "vitest";
import { generateMetadata } from "./page";

describe("cars search canonical", () => {
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
