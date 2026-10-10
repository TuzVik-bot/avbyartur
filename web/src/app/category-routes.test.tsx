import { expect, it } from "vitest";
import { categories } from "@/lib/listing-categories";
import { categoryPage, categoryMetadata } from "@/components/category-page";
import CarsPage from "./cars/page";
it.each(categories.filter(category => category.code !== "cars"))("forces $code route category in rendering and canonical metadata", async ({ code, label, href }) => {
 const props = { searchParams: Promise.resolve({ category_code: "cars", q: "Запрос", make_id: "foreign-car" }) };
 const page = await categoryPage(code, label)(props);
 expect(page.props.search).toEqual({ category_code: code, q: "Запрос" });
 const metadata = await categoryMetadata(code, label)(props);
 expect(metadata.alternates?.canonical).toBe(`https://suite-s1.denjik.by${href}?category_code=${code}&q=${encodeURIComponent("Запрос")}`);
});
it("forces cars in the actual search props", async () => {
 const page = await CarsPage({ searchParams: Promise.resolve({ category_code: "trucks", condition: "new" }) });
 expect(page.props.search).toEqual({ category_code: "cars", condition: "new" });
});
