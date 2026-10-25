import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Авторынок BY",
    short_name: "Авторынок",
    description: "Поиск автомобилей в Беларуси и подача объявлений.",
    id: "/",
    start_url: "/cars",
    scope: "/",
    display: "standalone",
    background_color: "#f8faff",
    theme_color: "#f4f6f5",
    prefer_related_applications: false,
    icons: [
      { src: "/pwa-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
    ]
  };
}
