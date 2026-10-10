import type { Metadata } from "next";
import { SearchRoute } from "./search-route";
import { categorySearch, type CategoryCode } from "@/lib/listing-categories";
import { readSearchParams, searchUrl } from "@/lib/search-state";
import { SITE_ORIGIN } from "@/lib/site-config";
type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };
export const categoryPage = (code: CategoryCode, title: string) => async ({ searchParams }: Props) => <SearchRoute title={title} search={categorySearch(code, readSearchParams(await searchParams))} />;
export const categoryMetadata = (code: CategoryCode, title: string) => async ({ searchParams }: Props): Promise<Metadata> => ({ title, alternates: { canonical: new URL(searchUrl(categorySearch(code, readSearchParams(await searchParams))), SITE_ORIGIN).toString() } });
