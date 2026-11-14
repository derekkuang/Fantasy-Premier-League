"use client";
// Reads ?view= so a link (or the old /differentials address) can open a specific view.

import { useSearchParams } from "next/navigation";
import type { PredictionRow } from "@/lib/api";
import { PlayersExplorer, type ViewId } from "@/components/players-explorer";

const IDS: ViewId[] = ["all", "low-owned", "budget", "pens", "run"];

export function PlayersFromUrl({ predictions, gw }: { predictions: PredictionRow[]; gw: number }) {
  const v = useSearchParams().get("view");
  const view = IDS.includes(v as ViewId) ? (v as ViewId) : "all";
  return <PlayersExplorer key={view} predictions={predictions} gw={gw} initialView={view} />;
}
