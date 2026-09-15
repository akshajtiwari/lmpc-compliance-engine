import { isConnectionError, type ApiClient } from "./api";
import {
  beginInspectionAttempt,
  beginInvestigationAttempt,
  blockedInspectionCount,
  completeInspection,
  completeInvestigation,
  getInvestigation,
  pendingInspectionCount,
  pendingInvestigations,
  queuedInspections,
  scheduleInspectionRetry,
  scheduleInvestigationRetry,
} from "./storage";
import { drainSequentially, nextRetryAt, SingleFlight } from "./sync-policy";
import type {
  AccountScope, Draft, LocalInspection, LocalInvestigation, ScanResult,
} from "./types";

export type SyncSummary = {
  attempted: number;
  completed: number;
  failed: number;
  remaining: number;
  /** Scans whose folder has not reached the server yet. Reported separately so the
   *  officer is told "waiting on 'Britannia'" rather than just "3 waiting". */
  blocked: number;
  stoppedForConnection: boolean;
  results: ScanResult[];
};

const outboxFlight = new SingleFlight<SyncSummary>();

function messageFrom(cause: unknown) {
  return cause instanceof Error ? cause.message : "Upload failed";
}

async function performSync(
  client: ApiClient,
  scope: AccountScope,
  clientUuid: string,
  draft: () => Draft,
  investigationId: string | null = null,
) {
  const attempts = await beginInspectionAttempt(clientUuid, scope);
  try {
    const result = await client.upload(draft(), investigationId);
    await completeInspection(clientUuid, scope, {scanId: result.scan_id, overall: result.overall});
    return result;
  } catch (cause) {
    await scheduleInspectionRetry(clientUuid, scope, messageFrom(cause), nextRetryAt(attempts));
    throw cause;
  }
}

export function syncDraft(
  client: ApiClient, scope: AccountScope, draft: Draft, investigationId?: string | null,
) {
  return performSync(client, scope, draft.clientUuid, () => draft, investigationId ?? null);
}

async function syncInvestigation(
  client: ApiClient, scope: AccountScope, row: LocalInvestigation,
) {
  const attempts = await beginInvestigationAttempt(row.client_uuid, scope);
  try {
    const folder = await client.createInvestigation({
      client_uuid: row.client_uuid,
      name: row.name,
      subject_brand: row.subject_brand,
      investigation_type: row.investigation_type,
      location_text: row.location_text,
    });
    await completeInvestigation(row.client_uuid, scope, folder.id);
    return folder;
  } catch (cause) {
    await scheduleInvestigationRetry(
      row.client_uuid, scope, messageFrom(cause), nextRetryAt(attempts));
    throw cause;
  }
}

async function syncStoredInspection(
  client: ApiClient, scope: AccountScope, row: LocalInspection,
) {
  // The row stores the device key of its folder; the server wants the server id, which
  // exists by now because phase one of the drain put it there.
  const folder = row.investigation_id
    ? await getInvestigation(row.investigation_id, scope)
    : null;
  return performSync(
    client, scope, row.client_uuid,
    () => JSON.parse(row.draft_json) as Draft,
    folder?.server_id ?? null,
  );
}

export function syncOutbox(
  client: ApiClient,
  scope: AccountScope,
  options: {includeDeferred?: boolean} = {},
) {
  return outboxFlight.run(async () => {
    // Two phases, one flight. A folder has to exist on the server before a scan can name
    // it, and an unready scan is excluded by the query rather than attempted and failed —
    // attempting it would burn a retry and push it an hour down the backoff ladder for a
    // reason that has nothing to do with the network.
    const folders = await pendingInvestigations(
      scope, {includeDeferred: options.includeDeferred});
    const foldersDrained = await drainSequentially(
      folders, (row) => syncInvestigation(client, scope, row), isConnectionError);
    if (foldersDrained.stopped) {
      return {
        attempted: foldersDrained.completed.length + foldersDrained.failures.length,
        completed: 0, failed: foldersDrained.failures.length,
        remaining: await pendingInspectionCount(scope),
        blocked: await blockedInspectionCount(scope),
        stoppedForConnection: true, results: [],
      };
    }
    const rows = await queuedInspections(scope, {includeDeferred: options.includeDeferred});
    const drained = await drainSequentially(
      rows,
      (row) => syncStoredInspection(client, scope, row),
      isConnectionError,
    );
    return {
      attempted: drained.completed.length + drained.failures.length,
      completed: drained.completed.length,
      failed: drained.failures.length,
      remaining: await pendingInspectionCount(scope),
      blocked: await blockedInspectionCount(scope),
      stoppedForConnection: drained.stopped,
      results: drained.completed,
    };
  });
}
