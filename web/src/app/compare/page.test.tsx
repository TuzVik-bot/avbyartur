import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import ComparePage from "./page";

vi.mock("@/components/comparison/comparison-view", () => ({
  ComparisonView: () => <div data-testid="comparison-view" />
}));

describe("compare page", () => {
  it("renders the comparison view", () => {
    expect(renderToStaticMarkup(<ComparePage />)).toContain('data-testid="comparison-view"');
  });
});
