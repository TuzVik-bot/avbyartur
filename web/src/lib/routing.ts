const APP_ORIGIN = "https://avbyartur.local";

export function safeNextPath(value: string | undefined) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) {
    return "/account";
  }

  try {
    const target = new URL(value, APP_ORIGIN);
    if (target.origin !== APP_ORIGIN) return "/account";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "/account";
  }
}
