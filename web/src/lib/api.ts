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

// --- per-player context: why a projection looks the way it does ------------------- //
// None of this moves a number — availability already reached the projection through the
// minutes model. It exists so the UI can EXPLAIN a number instead of just printing it.

/** `factor` is the exact multiplier availability applied to the minutes model: 0 for
 *  injured/suspended, chance/100 for doubtful, 1 otherwise. A player on 0.00 xP with
 *  factor 0 is flagged, not broken. */
export type Availability = {
  status: string | null;   // FPL code: a | d | i | s | u | n | o
  label: string | null;    // human form of the code ("doubtful")
  chance: number | null;   // chance_of_playing_next_round, 0-100
  factor: number;
  news: string;            // e.g. "Groin injury - Expected back 21 Aug"
  news_added: string | null;
};

export type Recent = {
  form: number;             // mean points over the last 30 days — 0 for everyone in preseason
  points_per_game: number;  // season-to-date; the honest fallback while form is still 0
  ep_next: number | null;   // FPL's OWN expected points — the benchmark this model is scored against
};

/** All zero until the season starts — prices do not move in preseason. */
export type PriceMoves = {
  change_event: number;    // £m moved this gameweek
  change_start: number;    // £m moved since the season began
  transfers_in: number;
  transfers_out: number;
  net_transfers: number;
};

/** Set-piece duty, 1 = first choice. null = no listed duty (the common case). */
export type SetPieces = {
  penalties: number | null;
  corners: number | null;
  freekicks: number | null;
};

export type PlayerContext = {
  availability: Availability;
  recent: Recent;
  price_moves: PriceMoves;
  set_pieces: SetPieces;
};

export type SquadPlayer = PlayerLite & PlayerContext & {
  position: "GK" | "DEF" | "MID" | "FWD";
  ownership: number;
  is_starter: boolean;
  is_captain: boolean;
  x_minutes?: number;
  diff_value?: number;
  template_risk?: number;
  risk_tier?: number;
  risk_label?: string;
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
  horizon?: number;  // gameweeks the precompute carried (optional: older payloads predate it)
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

// The gameweek to show: the latest one the backend has precomputed. Never hardcode a gw —
// the weekly precompute advances (gw1 -> gw2 -> ...) and the site must follow it, not 404.
export async function getLatestGw(): Promise<number> {
  try {
    const res = await fetch(`${API_URL}/health`, { next: { revalidate: 300 } });
    if (!res.ok) return 1;
    const body = (await res.json()) as { available_gws?: number[] };
    const gws = body.available_gws ?? [];
    return gws.length ? Math.max(...gws) : 1;
  } catch {
    return 1;
  }
}

// --- predictions (per-player xP, precomputed read) -------------------------------- #
export type PredictionFixture = {
  gw: number;
  opp: string;   // opponent club name
  home: boolean;
  xp: number;    // that gameweek's xP
  fdr: number;   // position-appropriate true FDR, 1..5
};

export type Prediction = PlayerContext & {
  element_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  team: string | null;
  price: number;
  xp: number;
  ownership: number;
  diff_value: number;                // xP × (1 − own%): what owning them gains vs the field
  template_risk: number;             // xP × own%: what NOT owning them costs vs the field
  risk_tier: number;                 // 1 Template .. 5 Deep punt — ownership only, NOT quality
  risk_label: string;                // the tier's name, e.g. "Differential"
  x_minutes: number;
  low_coverage: boolean;
  captain_score: number;
  xp_next3: number;                  // 3-week outlook (sum of the next 3 GWs)
  fixtures: PredictionFixture[];     // next 5, ordered
  breakdown: Breakdown | null;       // per-term xP split (Breakdown === the README's XpBreakdown)
};

export type PredictionsResponse = { meta: Meta; predictions: Prediction[] };

/** The lean shape a LIST row carries across the server->client boundary.
 *
 *  Everything a client component receives as props is serialised into the page HTML, and with
 *  555 players the full records made every list page ~1MB of markup — of which the heavy fields
 *  (`breakdown`, `recent`, `price_moves`, fixtures beyond the 3 the strip shows) were only ever
 *  read inside the detail sheet, one player at a time. Rows keep every scalar (cheap, and no
 *  component has to guess) plus `availability`/`set_pieces` (small objects the differentials
 *  rows render); the sheet fetches the rest from the API at the moment it opens. */
export type PredictionRow = Omit<Prediction, "breakdown" | "recent" | "price_moves">;

export function toRow(p: Prediction): PredictionRow {
  // Explicit deletes rather than destructure-and-discard: the linter is right that unused
  // bindings are noise, and the intent here IS deletion.
  const row: Partial<Prediction> = { ...p, fixtures: (p.fixtures ?? []).slice(0, 3) };
  delete row.breakdown;
  delete row.recent;
  delete row.price_moves;
  return row as PredictionRow;
}

/** One player's full record, fetched from the browser when the detail sheet opens. */
export async function getPlayerDetail(gw: number, elementId: number): Promise<Prediction> {
  const res = await fetch(`${API_URL}/predictions/${gw}/player/${elementId}`);
  if (!res.ok) throw new Error(`player detail failed (${res.status})`);
  return res.json();
}

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

// --- matches (per-fixture scoreline distribution + projected XIs + briefing) --------- #

/** One slot in a projected XI. Availability is already applied to `x_minutes` upstream. */
export type LineupPlayer = {
  element_id: number;
  web_name: string;
  position: "GK" | "DEF" | "MID" | "FWD";
  x_minutes: number;
  xp: number;
  price: number | null;
  status: string | null;      // FPL availability code
  chance: number | null;      // chance of playing next round, 0-100
  penalties: number | null;   // set-piece order, 1 = first choice
};

/** `confidence` is the XI's mean share of a full match — how nailed the side is, not a
 *  probability that the XI is exactly right. */
export type ProjectedLineup = {
  formation: string;          // e.g. "4-3-3"
  xi: LineupPlayer[];
  bench: LineupPlayer[];
  confidence: number;
};

/** A written read on the fixture. `generated_by` is either the model id or "template" — the
 *  deterministic fallback used whenever generation is unavailable or fails the numeric guard.
 *  `fact_pack` is every figure the prose was allowed to use, so a reader can check it. */
export type MatchBrief = {
  headline: string;
  angles: { text: string; evidence: string[] }[];
  generated_by: string;
  attempts?: number;
  rejected?: string[];        // why a generated briefing was refused, if one was
  fact_pack: Record<string, unknown>;
};

export type Scoreline = { home: number; away: number; p: number };

export type Match = {
  match_id: string;
  gw: number;
  home_id: number; home: string | null;
  away_id: number; away: string | null;
  source: "market" | "model";   // de-vigged betting line, or the Dixon-Coles engine
  lam_home: number; lam_away: number;
  result: { home_win: number; draw: number; away_win: number };
  btts: number;
  over_2_5: number;
  under_2_5: number;
  clean_sheet: { home: number; away: number };
  most_likely_score: [number, number];
  scorelines: Scoreline[];
  scorelines_p: number;         // probability mass the listed scorelines cover — the rest is tail
  fdr: {
    home: { attack: number; defence: number };
    away: { attack: number; defence: number };
  };
  lineups?: { home: ProjectedLineup | null; away: ProjectedLineup | null };
  brief?: MatchBrief;
};

export type MatchesResponse = { meta: Meta; matches: Match[] };
export type MatchResponse = { meta: Meta; match: Match; assets: Prediction[] };

/** Every fixture in the precomputed window, with its scoreline distribution. */
export async function getMatches(gw = 1): Promise<MatchesResponse> {
  const res = await fetch(`${API_URL}/matches/${gw}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`matches request failed (${res.status})`);
  return res.json();
}

/** One fixture, plus both clubs' players ranked by xP for that gameweek. */
export async function getMatch(gw: number, matchId: string): Promise<MatchResponse> {
  const res = await fetch(`${API_URL}/matches/${gw}/${matchId}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`match request failed (${res.status})`);
  return res.json();
}

// --- model card (how well the model actually does) ---------------------------------- #

export type CardSubset = {
  n: number;
  spearman_model: number | null;
  spearman_fpl: number | null;
  /** Error on the records the comparison actually rests on — see `baseline_gws`. */
  mae_model: number | null;
  /** Our error everywhere we scored, including gameweeks FPL published nothing for. */
  mae_model_all: number | null;
  mae_fpl: number | null;
  gws_model_mae_beats_fpl: string;
  /** How many gameweeks carried BOTH projections. The comparison is only this wide. */
  baseline_gws: number;
  baseline_n: number;
};

export type Experiment = {
  name: string;
  question: string;
  delta: string;
  verdict: string;
  measured: string;
};

export type ModelCard = {
  generated_at: string;
  season: string;
  model_ver: string;
  measured: {
    n_player_gws: number;
    gws_scored: number;
    played_only: CardSubset;
    all_players: CardSubset;
    mae_by_position_played: Record<string, number>;
  };
  method: Record<string, string>;
  experiments: Experiment[];
  not_modelled: { topic: string; detail: string }[];
};

/** The measured accuracy of the model. 404s until `scripts/build_model_card.py` has run —
 *  a page that publishes accuracy must never fall back to a placeholder number. */
export async function getModelCard(): Promise<ModelCard> {
  const res = await fetch(`${API_URL}/model`, { next: { revalidate: 3600 } });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `model card request failed (${res.status})`);
  }
  return res.json();
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

// --- team news (BETA) ---------------------------------------------------------------------- //
export type NewsMention = {
  element_id: number;
  name: string | null;
  /** FPL's OWN status code: a=available, d=doubtful, i=injured, s=suspended, u=unavailable. */
  fpl_status: string | null;
  /** FPL's OWN news line, verbatim. Never our paraphrase. */
  fpl_news: string;
};

export type NewsSource = "bbc" | "guardian" | "official";

export type NewsItem = {
  /** Which publisher carried it. A club's own statement and a rumour column are not the same
   *  evidence, and the page says which is which rather than blending them. */
  source?: NewsSource;
  title: string | null;
  summary: string | null;
  link: string | null;
  published: string | null;
  /** Keyword ROUTING hints, deliberately over-inclusive. Not classifications. */
  cues: string[];
  mentions: NewsMention[];
};

export type NewsResponse = {
  generated_at: string;
  n_items: number;
  n_clubs: number;
  clubs: Record<string, NewsItem[]>;
  quality: {
    precision: number | null;
    recall: number | null;
    additive: number;
    fpl_flagged: number;
  };
  beta: boolean;
  disclaimer: string;
};

/** Automated team-news digest. 404s until `make capture-news` has run — a team-news page with
 *  nothing captured must say so rather than render an empty state that reads as a quiet week. */
export async function getNews(): Promise<NewsResponse> {
  const res = await fetch(`${API_URL}/news`, { next: { revalidate: 900 } });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `news request failed (${res.status})`);
  }
  return res.json();
}
