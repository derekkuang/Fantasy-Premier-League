import type { MetadataRoute } from "next";
import { SITE_URL } from "./layout";

// Only the public, non-personalised routes. /team/{id} is deliberately excluded (see robots).
const ROUTES: [string, number, MetadataRoute.Sitemap[number]["changeFrequency"]][] = [
  ["/", 1.0, "weekly"],
  ["/squad", 0.9, "weekly"],
  ["/predictions", 0.9, "weekly"],
  ["/fixtures", 0.8, "weekly"],
  ["/differentials", 0.8, "weekly"],
  // Daily, because the capture is daily and stale team news is worse than none.
  ["/news", 0.6, "daily"],
  ["/model", 0.7, "monthly"],
  ["/privacy", 0.2, "yearly"],
  ["/terms", 0.2, "yearly"],
];

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map(([path, priority, changeFrequency]) => ({
    url: `${SITE_URL}${path}`,
    priority,
    changeFrequency,
  }));
}
