import * as SecureStore from "expo-secure-store";
import { openDatabaseAsync, type SQLiteDatabase } from "expo-sqlite";
import type {
  AccountScope, Draft, FolderRow, InvestigationDraft, LocalInspection,
  LocalInvestigation, Session,
} from "./types";

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
        CREATE TABLE IF NOT EXISTS investigations (
          client_uuid TEXT PRIMARY KEY NOT NULL,
          server_id TEXT,
          name TEXT NOT NULL,
          subject_brand TEXT,
          investigation_type TEXT NOT NULL DEFAULT 'OTHER',
          location_text TEXT,
          status TEXT NOT NULL DEFAULT 'OPEN',
          sync_state TEXT NOT NULL DEFAULT 'QUEUED',
          error TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT,
          last_attempt_at TEXT,
          synced_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          account_id TEXT NOT NULL,
          server_fingerprint TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_investigations_scope
          ON investigations (account_id, server_fingerprint, created_at DESC);
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
        // v3. investigation_id references investigations.client_uuid — the *device* key,
        // never the server id, because a folder created offline has no server id yet.
        ["investigation_id", "ALTER TABLE inspections ADD COLUMN investigation_id TEXT"],
        // captured_at is a date, so within one day a folder reordered itself every time a
        // retry touched updated_at. captured_ts carries the full instant.
        ["captured_ts", "ALTER TABLE inspections ADD COLUMN captured_ts TEXT"],
        // The server's verdict, cached so a past report opens with no network.
        ["result_json", "ALTER TABLE inspections ADD COLUMN result_json TEXT"],
        ["result_fetched_at", "ALTER TABLE inspections ADD COLUMN result_fetched_at TEXT"],
        ["remarks", "ALTER TABLE inspections ADD COLUMN remarks TEXT"],
      ] as const;
      for (const [column, statement] of migrations) {
        if (!columns.has(column)) await value.execAsync(statement);
      }
      await value.execAsync(
        "UPDATE inspections SET captured_ts = COALESCE(captured_ts, updated_at)"
        + " WHERE captured_ts IS NULL");
      await value.execAsync("CREATE INDEX IF NOT EXISTS idx_inspections_folder"
        + " ON inspections (account_id, server_fingerprint, investigation_id, captured_ts DESC)");
      await value.execAsync("PRAGMA user_version = 3");
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

export async function queueDraft(
  draft: Draft, scope: AccountScope, investigationId: string | null = null,
) {
  const value = await db();
  const now = new Date().toISOString();
  await value.runAsync(
    `INSERT INTO inspections (
       client_uuid, scan_id, captured_at, captured_ts, category, overall, state, error,
       draft_json, attempts, next_attempt_at, last_attempt_at, synced_at, account_id,
       server_fingerprint, investigation_id, updated_at
     ) VALUES (?, NULL, ?, ?, ?, NULL, 'QUEUED', NULL, ?, 0, NULL, NULL, NULL, ?, ?, ?, ?)
     ON CONFLICT(client_uuid) DO UPDATE SET
       draft_json=excluded.draft_json, state='QUEUED', error=NULL, attempts=0,
       next_attempt_at=NULL, last_attempt_at=NULL, synced_at=NULL,
       account_id=excluded.account_id, server_fingerprint=excluded.server_fingerprint,
       investigation_id=excluded.investigation_id, updated_at=excluded.updated_at`,
    draft.clientUuid, draft.capturedAt, now, draft.category, JSON.stringify(draft),
    scope.accountId, scope.serverFingerprint, investigationId, now,
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

/* ---- investigations ------------------------------------------------------------- */

export async function createInvestigation(draft: InvestigationDraft, scope: AccountScope) {
  const now = new Date().toISOString();
  await (await db()).runAsync(
    `INSERT INTO investigations (
       client_uuid, server_id, name, subject_brand, investigation_type, location_text,
       status, sync_state, attempts, created_at, updated_at, account_id, server_fingerprint
     ) VALUES (?, NULL, ?, ?, ?, ?, 'OPEN', 'QUEUED', 0, ?, ?, ?, ?)
     ON CONFLICT(client_uuid) DO UPDATE SET
       name=excluded.name, subject_brand=excluded.subject_brand,
       investigation_type=excluded.investigation_type,
       location_text=excluded.location_text, updated_at=excluded.updated_at`,
    draft.clientUuid, draft.name, draft.subjectBrand ?? null, draft.investigationType,
    draft.locationText ?? null, now, now, scope.accountId, scope.serverFingerprint,
  );
}

export async function listInvestigations(
  scope: AccountScope,
  options: {q?: string; status?: string; sort?: "recent" | "name"} = {},
): Promise<FolderRow[]> {
  const needle = `%${(options.q ?? "").trim().toLowerCase()}%`;
  const order = options.sort === "name" ? "i.name COLLATE NOCASE ASC" : "i.created_at DESC";
  return (await db()).getAllAsync<FolderRow>(
    `SELECT i.*,
            COUNT(s.client_uuid) AS scan_count,
            COALESCE(SUM(s.overall='NON_COMPLIANT'), 0) AS failed_count,
            COALESCE(SUM(s.state<>'COMPLETE'), 0) AS pending_count
     FROM investigations i
     LEFT JOIN inspections s ON s.investigation_id = i.client_uuid
     WHERE i.account_id=? AND i.server_fingerprint=?
       AND (?='%%' OR lower(i.name) LIKE ? OR lower(COALESCE(i.subject_brand,'')) LIKE ?
            OR lower(COALESCE(i.location_text,'')) LIKE ?)
       AND (? IS NULL OR i.status=?)
     GROUP BY i.client_uuid
     ORDER BY ${order}`,
    scope.accountId, scope.serverFingerprint, needle, needle, needle, needle,
    options.status ?? null, options.status ?? null,
  );
}

export async function getInvestigation(clientUuid: string, scope: AccountScope) {
  return (await db()).getFirstAsync<LocalInvestigation>(
    `SELECT * FROM investigations
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function investigationScans(clientUuid: string, scope: AccountScope) {
  return (await db()).getAllAsync<LocalInspection>(
    `SELECT * FROM inspections
     WHERE account_id=? AND server_fingerprint=? AND investigation_id=?
     ORDER BY captured_ts DESC, updated_at DESC`,
    scope.accountId, scope.serverFingerprint, clientUuid,
  );
}

export async function beginInvestigationAttempt(clientUuid: string, scope: AccountScope) {
  // Same compare-and-swap as beginInspectionAttempt; one locking scheme, not two.
  const value = await db();
  let attempts: number | null = null;
  const now = new Date().toISOString();
  await value.withExclusiveTransactionAsync(async (transaction) => {
    const result = await transaction.runAsync(
      `UPDATE investigations
       SET sync_state='SYNCING', attempts=attempts+1, next_attempt_at=NULL,
           last_attempt_at=?, error=NULL, updated_at=?
       WHERE client_uuid=? AND account_id=? AND server_fingerprint=?
         AND sync_state IN ('QUEUED','FAILED','SYNCING')`,
      now, now, clientUuid, scope.accountId, scope.serverFingerprint,
    );
    if (result.changes === 1) {
      const row = await transaction.getFirstAsync<{attempts: number}>(
        "SELECT attempts FROM investigations WHERE client_uuid=?", clientUuid);
      attempts = row?.attempts ?? null;
    }
  });
  if (attempts === null) throw new Error("This investigation is no longer available to sync");
  return attempts;
}

export async function completeInvestigation(
  clientUuid: string, scope: AccountScope, serverId: string,
) {
  const now = new Date().toISOString();
  await (await db()).runAsync(
    `UPDATE investigations
     SET sync_state='SYNCED', server_id=?, error=NULL, next_attempt_at=NULL,
         synced_at=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    serverId, now, now, clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function scheduleInvestigationRetry(
  clientUuid: string, scope: AccountScope, error: string, nextAttemptAt: string,
) {
  await (await db()).runAsync(
    `UPDATE investigations
     SET sync_state='FAILED', error=?, next_attempt_at=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    error.slice(0, 600), nextAttemptAt, new Date().toISOString(),
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function pendingInvestigations(
  scope: AccountScope, options: {includeDeferred?: boolean; now?: string} = {},
) {
  const now = options.now ?? new Date().toISOString();
  return (await db()).getAllAsync<LocalInvestigation>(
    `SELECT * FROM investigations
     WHERE account_id=? AND server_fingerprint=? AND server_id IS NULL
       AND sync_state IN ('QUEUED','FAILED','SYNCING')
       AND (?=1 OR next_attempt_at IS NULL OR next_attempt_at<=?)
     ORDER BY created_at`,
    scope.accountId, scope.serverFingerprint, options.includeDeferred ? 1 : 0, now,
  );
}

export async function cacheScanResult(
  clientUuid: string, scope: AccountScope, result: unknown,
) {
  const now = new Date().toISOString();
  await (await db()).runAsync(
    `UPDATE inspections SET result_json=?, result_fetched_at=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    JSON.stringify(result), now, now,
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function setScanRemarks(
  clientUuid: string, scope: AccountScope, remarks: string,
) {
  await (await db()).runAsync(
    `UPDATE inspections SET remarks=?, updated_at=?
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    remarks, new Date().toISOString(),
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function findInspection(clientUuid: string, scope: AccountScope) {
  return (await db()).getFirstAsync<LocalInspection>(
    `SELECT * FROM inspections
     WHERE client_uuid=? AND account_id=? AND server_fingerprint=?`,
    clientUuid, scope.accountId, scope.serverFingerprint,
  );
}

export async function allInspectionsForRetention(scope: AccountScope) {
  return (await db()).getAllAsync<LocalInspection>(
    `SELECT state, scan_id, synced_at, draft_json, result_json FROM inspections
     WHERE account_id=? AND server_fingerprint=?`,
    scope.accountId, scope.serverFingerprint,
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
       AND (investigation_id IS NULL OR EXISTS (
             SELECT 1 FROM investigations i
             WHERE i.client_uuid = inspections.investigation_id
               AND i.server_id IS NOT NULL))
     ORDER BY captured_at, updated_at`,
    scope.accountId, scope.serverFingerprint, options.includeDeferred ? 1 : 0, now,
  );
}

export async function blockedInspectionCount(scope: AccountScope) {
  /* Scans held back because their folder has not synced. A parent stuck at the end of
     the backoff ladder would otherwise hide its children with no explanation. */
  const row = await (await db()).getFirstAsync<{n: number}>(
    `SELECT COUNT(*) AS n FROM inspections
     WHERE account_id=? AND server_fingerprint=? AND state IN ('QUEUED','FAILED')
       AND investigation_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM investigations i
                       WHERE i.client_uuid = inspections.investigation_id
                         AND i.server_id IS NOT NULL)`,
    scope.accountId, scope.serverFingerprint,
  );
  return row?.n ?? 0;
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
