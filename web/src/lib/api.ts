// API client for the fpledge FastAPI backend.
//
// This is the ONLY place that knows the shapes the backend returns. Everything else
// imports these types, so if an endpoint changes you fix it here once. Think of the
// `type` blocks as the TypeScript equivalent of a Pydantic model / dataclass.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// A compact player, as returned inside a squad row or a transfer move.
export type PlayerLite = {
  element_id: number;
  web_name: string;
  team: string | null;
  price: number;
  xp: number;
};

// The per-term xP split — every *_points term sums to `total` (== the player's xp).
export type Breakdown = {
  p_play: number;
  p_60: number;
  x_goals: number;
  x_assists: number;
  p_clean_sheet: number;
  x_saves: number;
  p_dc_point: number;
  opp_lambda: number;
  appearance: number;
  goal_points: number;
  assist_points: number;
  cs_points: number;
  conceded_points: number;
  save_points: number;
  dc_points: number;
  bonus_points: number;
  total: number;
};

export type SquadPlayer = PlayerLite & {
  position: "GK" | "DEF" | "MID" | "FWD";
  ownership: number;
  is_starter: boolean;
  is_captain: boolean;
  x_minutes?: number;
  diff_value?: number;
  captain_score?: number;
  breakdown?: Breakdown | null;
};

export type TransferMove = {
  out: PlayerLite;
  in: PlayerLite;
  cost: number;      // price delta (£m)
  xp_gain: number;   // gross xP gain
  net_gain: number;  // xP gain net of the -4 hit
};

// [level, message] — level is "warn" | "info" | "ok"
export type BalanceFlag = [string, string];

export type Balance = {
  total_cost: number;
  budget_left: number;
  xi_xp: number;
  bench_spend: number;
  captain_dependence: number;
  n_template: number;
  n_differential: number;
  n_rotation_risk: number;
  flags: BalanceFlag[];
};

export type Meta = {
  gw: number;
  model_ver: string;
  run_ts: string;
  n_records: number;
};

export type TeamResponse = {
  meta: Meta;
  entry_id: number;
  gw: number;
  bank: number;
  free_transfers: number;
  projected_points: number | null;
  captain: { element_id: number; web_name: string; xp: number } | null;
  squad: SquadPlayer[];
  best_transfer: TransferMove | null;
  balance: Balance | null;
  unscored_elements: number[];
};

// --- predictions (per-player xP, precomputed read) -------------------------------- #
export type Prediction = {
  element_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team: string | null;
  price: number;
  xp: number;
  ownership: number;
  diff_value: number;
  x_minutes: number;
  low_coverage: boolean;
};

export type PredictionsResponse = { meta: Meta; predictions: Prediction[] };

/** Fetch the ranked per-player xP table for a gameweek (precomputed, cacheable). */
export async function getPredictions(gw = 1): Promise<PredictionsResponse> {
  const res = await fetch(`${API_URL}/predictions/${gw}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`predictions request failed (${res.status})`);
  return res.json();
}

// --- fixtures (true-FDR ticker) --------------------------------------------------- #
export type TickerFixture = {
  gw: number;
  opp_id: number;
  opp: string;          // opponent club name
  home: boolean;
  lam_for: number;      // model expected goals for
  lam_against: number;  // model expected goals against
  attack_fdr: number;   // 1 (easy to score) .. 5 (hard)
  defence_fdr: number;  // 1 (likely clean sheet) .. 5 (leaky)
};

export type FixturesResponse = {
  meta: Meta;
  start_gw: number;
  teams: { team_id: number; team_name: string; fixtures: TickerFixture[] }[];
};

/** Fetch the fixture ticker for a gameweek (precomputed). Cacheable — changes ~weekly. */
export async function getFixtures(gw = 1): Promise<FixturesResponse> {
  const res = await fetch(`${API_URL}/fixtures/${gw}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`fixtures request failed (${res.status})`);
  return res.json();
}

/** team name -> its upcoming fixtures, as a plain object (serialisable to Client Components). */
export function fixturesByTeam(resp: FixturesResponse): Record<string, TickerFixture[]> {
  return Object.fromEntries(resp.teams.map((t) => [t.team_name, t.fixtures]));
}

/** The FDR a given position cares about: GK/DEF want a clean sheet, MID/FWD want goals. */
export function fdrFor(position: string, fx: TickerFixture): number {
  return position === "GK" || position === "DEF" ? fx.defence_fdr : fx.attack_fdr;
}

/** Fetch a manager's personalised dashboard. Throws Error(detail) on a 4xx/5xx. */
export async function getTeam(entryId: string, gw = 1): Promise<TeamResponse> {
  // no-store: this is per-user and cheap; never cache it at the framework layer.
  const res = await fetch(`${API_URL}/team/${entryId}?gw=${gw}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}
