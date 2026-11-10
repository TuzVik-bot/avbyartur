import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import CarsLoading from "./loading";

describe("cars loading state", () => {
  it("announces the listing search load with a busy skeleton", () => {
    const html = renderToStaticMarkup(<CarsLoading />);

    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("route-skeleton");
    expect(html).toContain('role="status"');
    expect(html).toContain("Загружаем объявления…");
  });
});
