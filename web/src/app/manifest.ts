import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Авторынок BY",
    short_name: "Авторынок",
    description: "Поиск автомобилей в Беларуси и подача объявлений.",
    start_url: "/",
    display: "standalone",
    background_color: "#f8faff",
    theme_color: "#f4f6f5",
    icons: [
      { src: "/icon1", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon2", sizes: "512x512", type: "image/png", purpose: "maskable" }
    ]
  };
}
