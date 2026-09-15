/* Folder statistics, derived.
 *
 * Pure so it can be unit tested: it imports no React and no Expo module. Nothing here is
 * stored — a counter column would drift the moment a reviewer overrides a verdict or a
 * re-evaluation batch lands, and drift is exactly what this product cannot have. */
import type { LocalInspection } from "./types";

export type FolderStats = {
  total: number;
  compliant: number;
  failing: number;
  unclear: number;
  pending: number;
  evaluated: number;
  /** How many of the scans had a cached report to read findings out of. Reported so the
   *  screen can say "from 3 of 9 reports" instead of silently under-counting violations. */
  withReports: number;
  topViolations: {check: string; count: number}[];
};

export function summarise(rows: LocalInspection[]): FolderStats {
  const stats: FolderStats = {
    total: rows.length, compliant: 0, failing: 0, unclear: 0, pending: 0,
    evaluated: 0, withReports: 0, topViolations: [],
  };
  const counts = new Map<string, number>();
  for (const row of rows) {
    if (row.state !== "COMPLETE") { stats.pending += 1; continue; }
    if (row.overall) stats.evaluated += 1;
    if (row.overall === "COMPLIANT") stats.compliant += 1;
    else if (row.overall === "NON_COMPLIANT") stats.failing += 1;
    else if (row.overall) stats.unclear += 1;
    if (!row.result_json) continue;
    let cached: {evaluations?: {check: string; outcome: string}[]};
    try { cached = JSON.parse(row.result_json); }
    catch { continue; }          // a truncated cache is not worth failing a screen over
    stats.withReports += 1;
    for (const item of cached.evaluations ?? []) {
      if (item.outcome === "FAIL") counts.set(item.check, (counts.get(item.check) ?? 0) + 1);
    }
  }
  stats.topViolations = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([check, count]) => ({check, count}));
  return stats;
}
