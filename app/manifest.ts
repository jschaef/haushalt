import type { MetadataRoute } from "next";

// Installable as an app on the phone's home screen (PWA).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Haushalt",
    short_name: "Haushalt",
    description: "Household spending at a glance",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#14121f",
    theme_color: "#14121f",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
    shortcuts: [{ name: "Scan receipt", url: "/receipts?scan=1" }],
  };
}
