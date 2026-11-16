import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Predictions and Differentials became one Players page. Old links, bookmarks and search
  // results keep working, and Differentials lands on the Low owned view it used to be.
  async redirects() {
    return [
      { source: "/predictions", destination: "/players", permanent: true },
      { source: "/differentials", destination: "/players?view=low-owned", permanent: true },
      // The match page moved into the Match Lab (docs/MATCH_LAB.md); old links keep working.
      { source: "/fixtures/:match(\\d{1,2}-\\d{1,2}-\\d{1,2})", destination: "/match-lab/:match", permanent: true },
    ];
  },
};

export default nextConfig;
