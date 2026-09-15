/* What may be deleted from this phone, and when.
 *
 * Pure policy: it decides, a thin caller does the filesystem work. Two directories grow
 * without bound today — evidence photographs are never removed after a sync (and every
 * retake leaks a full-resolution JPEG), and downloaded reports are never cleaned at all.
 *
 * Evidence is legal material, so the rules here are deliberately conservative: a panel is
 * only ever deleted when its inspection is complete, has a server id, synced longer ago
 * than the retention window, and the server confirmed the same SHA-256 it was given. */

export type StoredFile = {uri: string; size: number; modifiedAt: number};

export type InspectionForRetention = {
  state: string;
  scan_id: string | null;
  synced_at: string | null;
  draft_json: string;
  result_json: string | null;
};

export const DEFAULT_RETENTION_DAYS = 30;
export const REPORT_CACHE_DAYS = 7;
export const REPORT_CACHE_BYTES = 100 * 1024 * 1024;

const DAY = 86_400_000;

/** Every evidence file a draft still points at. */
export function referencedUris(rows: InspectionForRetention[]): Set<string> {
  const live = new Set<string>();
  for (const row of rows) {
    let draft: {panels?: {uri?: string}[]};
    try { draft = JSON.parse(row.draft_json); } catch { continue; }
    for (const panel of draft.panels ?? []) if (panel.uri) live.add(panel.uri);
  }
  return live;
}

/** Files under evidence/ that no draft references any more.
 *
 *  Filename-driven cleanup is not possible: each photograph is written under a fresh
 *  random UUID, not the draft's client UUID, so the only record of which file belongs to
 *  which inspection is the draft itself. This is also what catches retake leaks. */
export function orphanedEvidence(
  files: StoredFile[], rows: InspectionForRetention[],
): string[] {
  const live = referencedUris(rows);
  return files.filter((file) => !live.has(file.uri)).map((file) => file.uri);
}

/** Panels of inspections that are safely behind us. */
export function expiredEvidence(
  rows: InspectionForRetention[],
  options: {now?: number; retentionDays?: number} = {},
): string[] {
  const now = options.now ?? Date.now();
  const window = (options.retentionDays ?? DEFAULT_RETENTION_DAYS) * DAY;
  const doomed: string[] = [];
  for (const row of rows) {
    if (row.state !== "COMPLETE" || !row.scan_id || !row.synced_at) continue;
    if (now - Date.parse(row.synced_at) < window) continue;
    let draft: {panels?: {uri?: string; sha256?: string}[]};
    let result: {images?: {sha256?: string}[]};
    try {
      draft = JSON.parse(row.draft_json);
      result = row.result_json ? JSON.parse(row.result_json) : {};
    } catch { continue; }
    // Without the server's own list of hashes we cannot prove it holds this evidence.
    const held = new Set((result.images ?? []).map((image) => image.sha256));
    if (held.size === 0) continue;
    for (const panel of draft.panels ?? []) {
      if (panel.uri && panel.sha256 && held.has(panel.sha256)) doomed.push(panel.uri);
    }
  }
  return doomed;
}

/** Downloaded reports are a pure cache: age out, then trim to a size cap, oldest first. */
export function expiredReports(
  files: StoredFile[],
  options: {now?: number; days?: number; capBytes?: number} = {},
): string[] {
  const now = options.now ?? Date.now();
  const days = options.days ?? REPORT_CACHE_DAYS;
  const cap = options.capBytes ?? REPORT_CACHE_BYTES;
  const old = files.filter((file) => now - file.modifiedAt > days * DAY);
  const doomed = new Set(old.map((file) => file.uri));

  const remaining = files.filter((file) => !doomed.has(file.uri))
    .sort((a, b) => a.modifiedAt - b.modifiedAt);
  let total = remaining.reduce((sum, file) => sum + file.size, 0);
  for (const file of remaining) {
    if (total <= cap) break;
    doomed.add(file.uri);
    total -= file.size;
  }
  return [...doomed];
}
