import { isConnectionError, type ApiClient } from "./api";
import {
  beginInspectionAttempt,
  completeInspection,
  pendingInspectionCount,
  queuedInspections,
  scheduleInspectionRetry,
} from "./storage";
import { drainSequentially, nextRetryAt, SingleFlight } from "./sync-policy";
import type { AccountScope, Draft, LocalInspection, ScanResult } from "./types";

export type SyncSummary = {
  attempted: number;
  completed: number;
  failed: number;
  remaining: number;
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
) {
  const attempts = await beginInspectionAttempt(clientUuid, scope);
  try {
    const result = await client.upload(draft());
    await completeInspection(clientUuid, scope, {scanId: result.scan_id, overall: result.overall});
    return result;
  } catch (cause) {
    await scheduleInspectionRetry(clientUuid, scope, messageFrom(cause), nextRetryAt(attempts));
    throw cause;
  }
}

export function syncDraft(client: ApiClient, scope: AccountScope, draft: Draft) {
  return performSync(client, scope, draft.clientUuid, () => draft);
}

function syncStoredInspection(client: ApiClient, scope: AccountScope, row: LocalInspection) {
  return performSync(
    client,
    scope,
    row.client_uuid,
    () => JSON.parse(row.draft_json) as Draft,
  );
}

export function syncOutbox(
  client: ApiClient,
  scope: AccountScope,
  options: {includeDeferred?: boolean} = {},
) {
  return outboxFlight.run(async () => {
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
      stoppedForConnection: drained.stopped,
      results: drained.completed,
    };
  });
}
