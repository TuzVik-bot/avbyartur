// The saved-search API and its database column have bounded lengths.
export function savedSearchLimitMessage(url: string): string | null {
  const parsed = new URL(url, "http://localhost");
  if (url.length > 2048) return "Ссылка слишком длинная для сохранения. Уберите часть фильтров.";
  for (const [key, value] of parsed.searchParams) {
    if (value.length > 500) return "Слишком много значений в одном фильтре для сохранения. Уберите часть марок или моделей.";
    if (key === "make_ids" || key === "model_ids") {
      const ids = value.split(",").map((id) => id.trim().replaceAll("-", "").toLowerCase());
      if (ids.every((id) => /^[0-9a-f]{32}$/.test(id))) {
        const normalized = [...new Set(ids)].sort().map((id) => `${id.slice(0, 8)}-${id.slice(8, 12)}-${id.slice(12, 16)}-${id.slice(16, 20)}-${id.slice(20)}`).join(",");
        if (normalized.length > 500) return "Для сохранения выберите не больше 13 марок и 13 моделей.";
        parsed.searchParams.set(key, normalized);
      }
    }
  }
  const canonicalUrl = `${parsed.pathname}${parsed.searchParams.size ? `?${parsed.searchParams.toString()}` : ""}`;
  return canonicalUrl.length > 2048 ? "Ссылка слишком длинная для сохранения. Уберите часть фильтров." : null;
}
