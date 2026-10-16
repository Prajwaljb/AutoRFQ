import type { Flag, ReviewFlag, RunSummary } from "./types";

/** Needs review first (oldest waiting first), then everything else newest first. */
export function sortRuns(runs: RunSummary[]): RunSummary[] {
  return [...runs].sort((a, b) => {
    const ar = a.status === "needs_review" ? 0 : 1;
    const br = b.status === "needs_review" ? 0 : 1;
    if (ar !== br) return ar - br;
    if (ar === 0) return a.updated - b.updated;
    return b.updated - a.updated;
  });
}

const SEVERITY: Record<string, number> = { high: 0, medium: 1, low: 2, info: 3 };

/** Flags grouped by item in email order, high to low severity within an item. */
export function sortFlags<T extends Flag | ReviewFlag>(flags: T[], itemOrder: string[]): T[] {
  const pos = (pid: string) => {
    const i = itemOrder.indexOf(pid);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...flags].sort(
    (a, b) =>
      pos(a.product_id) - pos(b.product_id) ||
      (SEVERITY[a.severity] ?? 9) - (SEVERITY[b.severity] ?? 9) ||
      a.column.localeCompare(b.column),
  );
}

export type RunTab = "needs_review" | "processing" | "ready" | "sent" | "failed" | "all";

export function tabOf(status: RunSummary["status"]): Exclude<RunTab, "all"> {
  if (status === "needs_review") return "needs_review";
  if (status === "processing") return "processing";
  if (status === "sent") return "sent";
  if (status === "failed" || status === "fallback_sent") return "failed";
  return "ready"; // ready and approved: the RFQ is built, the reply not sent yet
}
