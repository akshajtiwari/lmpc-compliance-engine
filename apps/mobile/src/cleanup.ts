/* Apply the retention policy to this phone's filesystem.
 *
 * The decisions all live in retention.ts, which is pure and tested. This only walks the
 * two directories and deletes what it is told to. */
import { Directory, File, Paths } from "expo-file-system";

import {
  expiredEvidence, expiredReports, orphanedEvidence,
  type InspectionForRetention, type StoredFile,
} from "./retention";

function listing(directory: Directory): StoredFile[] {
  if (!directory.exists) return [];
  const files: StoredFile[] = [];
  for (const entry of directory.list()) {
    if (!(entry instanceof File)) continue;
    files.push({uri: entry.uri, size: entry.size ?? 0,
                modifiedAt: entry.modificationTime ?? 0});
  }
  return files;
}

function remove(uris: string[]): number {
  let removed = 0;
  for (const uri of uris) {
    try {
      const file = new File(uri);
      if (file.exists) { file.delete(); removed += 1; }
    } catch { /* a file already gone is the outcome we wanted */ }
  }
  return removed;
}

export type CleanupSummary = {evidence: number; reports: number};

export function sweep(
  rows: InspectionForRetention[], options: {retentionDays?: number} = {},
): CleanupSummary {
  const evidenceDir = new Directory(Paths.document, "evidence");
  const reportsDir = new Directory(Paths.cache, "reports");
  const evidence = remove([
    ...orphanedEvidence(listing(evidenceDir), rows),
    ...expiredEvidence(rows, {retentionDays: options.retentionDays}),
  ]);
  return {evidence, reports: remove(expiredReports(listing(reportsDir)))};
}
