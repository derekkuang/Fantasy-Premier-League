// Club identity for the pitch view: colours + short code + kit pattern per club.
// These are factual club colours applied to a GENERIC shirt shape — no official kits or
// crests (matches the design's brief and keeps us clear of trademark issues). Keys match
// the team names the API returns (from fpl_teams).

export type KitPattern = "solid" | "stripes" | "sash";
export type Club = { primary: string; secondary: string; text: string; shortCode: string; pattern: KitPattern };

export const CLUB_COLOURS: Record<string, Club> = {
  "Arsenal": { primary: "#EF0107", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "ARS", pattern: "solid" },
  "Aston Villa": { primary: "#670E36", secondary: "#95BFE5", text: "#FFFFFF", shortCode: "AVL", pattern: "solid" },
  "Bournemouth": { primary: "#DA291C", secondary: "#000000", text: "#FFFFFF", shortCode: "BOU", pattern: "stripes" },
  "Brentford": { primary: "#D20000", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "BRE", pattern: "stripes" },
  "Brighton": { primary: "#0057B8", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "BHA", pattern: "stripes" },
  "Chelsea": { primary: "#034694", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "CHE", pattern: "solid" },
  "Coventry City": { primary: "#78D0F3", secondary: "#FFFFFF", text: "#08324A", shortCode: "COV", pattern: "solid" },
  "Crystal Palace": { primary: "#1B458F", secondary: "#C4122E", text: "#FFFFFF", shortCode: "CRY", pattern: "sash" },
  "Everton": { primary: "#003399", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "EVE", pattern: "solid" },
  "Fulham": { primary: "#FFFFFF", secondary: "#000000", text: "#171717", shortCode: "FUL", pattern: "solid" },
  "Hull City": { primary: "#F5A12D", secondary: "#000000", text: "#171717", shortCode: "HUL", pattern: "stripes" },
  "Ipswich Town": { primary: "#3A64A3", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "IPS", pattern: "solid" },
  "Leeds": { primary: "#FFFFFF", secondary: "#1D428A", text: "#171717", shortCode: "LEE", pattern: "solid" },
  "Liverpool": { primary: "#C8102E", secondary: "#00B2A9", text: "#FFFFFF", shortCode: "LIV", pattern: "solid" },
  "Man City": { primary: "#6CABDD", secondary: "#1C2C5B", text: "#0B1A33", shortCode: "MCI", pattern: "solid" },
  "Man Utd": { primary: "#DA291C", secondary: "#FBE122", text: "#FFFFFF", shortCode: "MUN", pattern: "solid" },
  "Newcastle": { primary: "#241F20", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "NEW", pattern: "stripes" },
  "Nott'm Forest": { primary: "#DD0000", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "NFO", pattern: "solid" },
  "Spurs": { primary: "#FFFFFF", secondary: "#132257", text: "#171717", shortCode: "TOT", pattern: "solid" },
  "Sunderland": { primary: "#EB172B", secondary: "#FFFFFF", text: "#FFFFFF", shortCode: "SUN", pattern: "stripes" },
};

const NEUTRAL: Club = { primary: "#6b7280", secondary: "#e5e7eb", text: "#FFFFFF", shortCode: "???", pattern: "solid" };

/** Club identity for a team name, with a neutral fallback + derived short code for unknowns. */
export function getClub(team: string | null | undefined): Club {
  if (!team) return NEUTRAL;
  const hit = CLUB_COLOURS[team];
  if (hit) return hit;
  return { ...NEUTRAL, shortCode: team.replace(/[^A-Za-z]/g, "").slice(0, 3).toUpperCase() || "???" };
}

// True-FDR colour scale, 1 (easiest) → 5 (hardest). White digit sits on top, so each
// colour is dark enough for legible contrast.
const FDR_COLOURS: Record<number, string> = {
  1: "#16a34a", // green
  2: "#4d7c0f", // olive-green
  3: "#6b7280", // grey (neutral)
  4: "#ea580c", // orange
  5: "#b91c1c", // red
};

export function fdrColour(rating: number): string {
  return FDR_COLOURS[rating] ?? FDR_COLOURS[3];
}
