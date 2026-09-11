import * as SecureStore from "expo-secure-store";
import { openDatabaseAsync, type SQLiteDatabase } from "expo-sqlite";
import type { AccountScope, Draft, LocalInspection, Session } from "./types";

const SESSION_KEY = "lmpc.session.v1";
let database: Promise<SQLiteDatabase> | null = null;

async function db() {
  if (!database) {
    database = openDatabaseAsync("lmpc-field.db").then(async (value) => {
      await value.execAsync(`
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS inspections (
          client_uuid TEXT PRIMARY KEY NOT NULL,
          scan_id TEXT,
          captured_at TEXT NOT NULL,
          category TEXT NOT NULL,
          overall TEXT,
          state TEXT NOT NULL,
          error TEXT,
          draft_json TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT,
          last_attempt_at TEXT,
          synced_at TEXT,
          account_id TEXT,
          server_fingerprint TEXT,
          updated_at TEXT NOT NULL
        );
      `);
      const columns = new Set(
        (await value.getAllAsync<{name: string}>("PRAGMA table_info(inspections)"))
          .map((column) => column.name),
      );
      const migrations = [
        ["attempts", "ALTER TABLE inspections ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"],
        ["next_attempt_at", "ALTER TABLE inspections ADD COLUMN next_attempt_at TEXT"],
        ["last_attempt_at", "ALTER TABLE inspections ADD COLUMN last_attempt_at TEXT"],
        ["synced_at", "ALTER TABLE inspections ADD COLUMN synced_at TEXT"],
        ["account_id", "ALTER TABLE inspections ADD COLUMN account_id TEXT"],
        ["server_fingerprint", "ALTER TABLE inspections ADD COLUMN server_fingerprint TEXT"],
      ] as const;
      for (const [column, statement] of migrations) {
        if (!columns.has(column)) await value.execAsync(statement);
      }
      await value.execAsync("PRAGMA user_version = 2");
      return value;
    });
  }
  return database;
}

export async function loadSession(): Promise<Session | null> {
  const raw = await SecureStore.getItemAsync(SESSION_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw) as Session; } catch { await SecureStore.deleteItemAsync(SESSION_KEY); return null; }
}

export async function saveSession(session: Session | null) {
  if (session) {
    const persisted = {...session, accessToken: ""};
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(persisted), {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  } else {
    await SecureStore.deleteItemAsync(SESSION_KEY);
  }
}

export function accountScope(session: Session): AccountScope {
  return {accountId: session.user.id, serverFingerprint: session.fingerprint};
}

async function claimLegacyInspections(scope: AccountScope) {
  const value = await db();
  await value.runAsync(
    `UPDATE inspections
     SET account_id=?, server_fingerprint=?, updated_at=?
     WHERE account_id IS NULL AND server_fingerprint IS NULL`,
    scope.accountId, scope.serverFingerprint, new Date().toISOString(),
  );
}

export async function queueDraft(draft: Draft, scope: AccountScope) {
  const value = await db();
  await value.runAsync(
    `INSERT INTO inspections (
       client_uuid, scan_id, captured_at, category, overall, state, error, draft_json,
       attempts, next_attempt_at, last_attempt_at, synced_at, account_id, server_fingerprint, updated_at
     ) VALUES (?, NULL, ?, ?, NULL, 'QUEUED', NULL, ?, 0, NULL, NULL, NULL, ?, ?, ?)
     ON CONFLICT(client_uuid) DO UPDATE SET
       draft_json=excluded.draft_json, state='QUEUED', error=NULL, attempts=0,
       next_attempt_at=NULL, last_attempt_at=NULL, synced_at=NULL,
       account_id=excluded.account_id, server_fingerprint=excluded.server_fingerprint,
       updated_at=excluded.updated_at`,
    draft.clientUuid, draft.capturedAt, draft.category, JSON.stringify(draft),
    scope.accountId, scope.serverFingerprint, new Date().toISOString(),
  );
}

export async function beginInspectionAttempt(clientUuid: string, scope: AccountScope) {
  const value = await db();
  let attempts: number | null = null;
  const now = new Date().toISOString();
  await value.withExclusiveTransactionAsync(async (transaction) => {
    const result = await transaction.runAsync(
      `UPDATE inspections
       SET state='UPLOADING', attempts=attempts+1, next_attempt_at=NULL,
           last_attempt_at=?, error=NULL, updated_at=?
       WHERE client_uuid=? AND account_id=? AND server_fingerprint=?
         AND state IN ('QUEUED','FAILED','UPLOADING')`,
      now, now, clientUuid, scope.accountId, scope.serverFingerprint,
    );
    if (result.changes === 1) {
      const row = await transaction.getFirstAsync<{attempts: number}>(
        "SELECT attempts FROM inspections WHERE client_uuid=?",
        clientUuid,
      );
      attempts = row?.attempts ?? null;
    }
  });
  if (attempts === null) throw new Error("This inspection is no longer available to sync");
  return attempts;
}

export async function completeInspection(
  clientUuid: string,
  scope: AccountScope,
  values: {scanId: string; overall: string | null},
) {
  const now = new Date().toISOString();
  await (await db()).runAsync(
    `UPDATE inspections
     SET state='COMPLETE', scan_id=?, overall=?, error=NULL, next_attempt_at=NULL,
         synced_at=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    values.scanId, values.overall, now, now,
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function scheduleInspectionRetry(
  clientUuid: string,
  scope: AccountScope,
  error: string,
  nextAttemptAt: string,
) {
  await (await db()).runAsync(
    `UPDATE inspections
     SET state='FAILED', error=?, next_attempt_at=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    error.slice(0, 600), nextAttemptAt, new Date().toISOString(),
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function recentInspections(scope: AccountScope) {
  await claimLegacyInspections(scope);
  return (await db()).getAllAsync<LocalInspection>(
    `SELECT * FROM inspections
     WHERE account_id=? AND server_fingerprint=?
     ORDER BY captured_at DESC, updated_at DESC LIMIT 30`,
    scope.accountId, scope.serverFingerprint,
  );
}

export async function queuedInspections(
  scope: AccountScope,
  options: {includeDeferred?: boolean; now?: string} = {},
) {
  // UPLOADING is recoverable after a process kill or network interruption. Reusing the
  // same client UUID makes the server-side create operation idempotent.
  await claimLegacyInspections(scope);
  const now = options.now ?? new Date().toISOString();
  return (await db()).getAllAsync<LocalInspection>(
    `SELECT * FROM inspections
     WHERE account_id=? AND server_fingerprint=?
       AND state IN ('QUEUED','FAILED','UPLOADING')
       AND (?=1 OR state IN ('QUEUED','UPLOADING') OR next_attempt_at IS NULL OR next_attempt_at<=?)
     ORDER BY captured_at, updated_at`,
    scope.accountId, scope.serverFingerprint, options.includeDeferred ? 1 : 0, now,
  );
}

export async function pendingInspectionCount(scope: AccountScope) {
  await claimLegacyInspections(scope);
  const row = await (await db()).getFirstAsync<{count: number}>(
    `SELECT COUNT(*) AS count FROM inspections
     WHERE account_id=? AND server_fingerprint=?
       AND state IN ('QUEUED','FAILED','UPLOADING')`,
    scope.accountId, scope.serverFingerprint,
  );
  return row?.count ?? 0;
}
