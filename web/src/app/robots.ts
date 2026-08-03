import type { MetadataRoute } from "next";
import { SITE_URL } from "./layout";

// /team/* is per-manager and built from a user-supplied id — there is nothing there worth
// indexing, and crawling it would fire one upstream FPL API call per crawled id.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: "/team/" }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
