import * as SecureStore from "expo-secure-store";
import { openDatabaseAsync, type SQLiteDatabase } from "expo-sqlite";
import type { Draft, LocalInspection, Session } from "./types";

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
          updated_at TEXT NOT NULL
        );
      `);
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

export async function queueDraft(draft: Draft) {
  const value = await db();
  await value.runAsync(
    `INSERT INTO inspections (client_uuid, scan_id, captured_at, category, overall, state, error, draft_json, updated_at)
     VALUES (?, NULL, ?, ?, NULL, 'QUEUED', NULL, ?, ?)
     ON CONFLICT(client_uuid) DO UPDATE SET draft_json=excluded.draft_json, state='QUEUED', error=NULL, updated_at=excluded.updated_at`,
    draft.clientUuid, draft.capturedAt, draft.category, JSON.stringify(draft), new Date().toISOString(),
  );
}

export async function markInspection(clientUuid: string, state: LocalInspection["state"], values: {scanId?: string; overall?: string | null; error?: string | null} = {}) {
  const value = await db();
  await value.runAsync(
    "UPDATE inspections SET state=?, scan_id=COALESCE(?,scan_id), overall=?, error=?, updated_at=? WHERE client_uuid=?",
    state, values.scanId ?? null, values.overall ?? null, values.error ?? null, new Date().toISOString(), clientUuid,
  );
}

export async function recentInspections() {
  return (await db()).getAllAsync<LocalInspection>("SELECT * FROM inspections ORDER BY captured_at DESC LIMIT 30");
}

export async function queuedInspections() {
  // UPLOADING is recoverable after a process kill or network interruption. Reusing the
  // same client UUID makes the server-side create operation idempotent.
  return (await db()).getAllAsync<LocalInspection>(
    "SELECT * FROM inspections WHERE state IN ('QUEUED','FAILED','UPLOADING') ORDER BY captured_at",
  );
}
