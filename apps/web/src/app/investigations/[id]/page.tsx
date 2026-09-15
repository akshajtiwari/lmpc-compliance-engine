"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { StatusPill } from "@/components/status-pill";
import type { Investigation, InvestigationNote, InvestigationStats, ScanSummary } from "@/lib/types";

export default function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const { api, user } = useAuth();
  const [folder, setFolder] = useState<Investigation | null>(null);
  const [stats, setStats] = useState<InvestigationStats | null>(null);
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [notes, setNotes] = useState<InvestigationNote[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    Promise.all([
      api<Investigation>(`/investigations/${id}`),
      api<InvestigationStats>(`/investigations/${id}/stats`),
      api<{ items: ScanSummary[] }>(`/investigations/${id}/scans?page_size=100`),
      api<{ items: InvestigationNote[] }>(`/investigations/${id}/notes`),
    ]).then(([one, summary, page, noted]) => {
      setFolder(one); setStats(summary); setScans(page.items); setNotes(noted.items);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not open this investigation"));
  }, [api, id]);
  useEffect(load, [load]);

  async function addNote(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    try { await api(`/investigations/${id}/notes`, { method: "POST", body: JSON.stringify({ body: note.trim() }) }); setNote(""); load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save that note"); }
    finally { setBusy(false); }
  }

  async function toggleStatus() {
    if (!folder) return;
    setBusy(true);
    try { await api(`/investigations/${id}`, { method: "PATCH", body: JSON.stringify({ status: folder.status === "OPEN" ? "CLOSED" : "OPEN" }) }); load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not change the status"); }
    finally { setBusy(false); }
  }

  async function makeReport(kind: "FIELD" | "FINALIZED") {
    setBusy(true); setError("");
    try {
      const made = await api<{ report_id: string }>(`/investigations/${id}/report?kind=${kind}`, { method: "POST" });
      window.open(`/api/v1/reports/${made.report_id}/download?format=pdf`, "_blank");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not produce that report"); }
    finally { setBusy(false); }
  }

  if (error && !folder) return <AppShell><div className="error">{error}</div></AppShell>;
  if (!folder || !stats) return <AppShell><div className="empty">Opening investigation…</div></AppShell>;

  return <AppShell>
    <div className="page-head">
      <div>
        <p className="eyebrow">Case file</p>
        <h1>{folder.name}</h1>
        <p>{[folder.subject_brand, folder.location_text, folder.investigation_type.replaceAll("_", " ").toLowerCase()].filter(Boolean).join(" · ")}</p>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="button secondary" disabled={busy} onClick={() => makeReport("FIELD")}>Investigation report</button>
        {user?.permissions.includes("reports:create") && <button className="button secondary" disabled={busy} onClick={() => makeReport("FINALIZED")}>Finalise report</button>}
        {user?.permissions.includes("investigations:update") && <button className="button secondary" disabled={busy} onClick={toggleStatus}>{folder.status === "OPEN" ? "Close" : "Reopen"}</button>}
      </div>
    </div>
    {error && <div className="error">{error}</div>}

    <div className="toolbar">
      <span className="muted small">{stats.scan_count} product{stats.scan_count === 1 ? "" : "s"}</span>
      {Object.entries(stats.by_overall).map(([outcome, count]) => <StatusPill key={outcome} value={`${count} ${outcome}`} />)}
      {stats.pending_count > 0 && <span className="muted small">{stats.pending_count} still processing</span>}
      <StatusPill value={folder.status} />
    </div>

    {stats.top_violations.length > 0 && <div className="notice">
      <strong>Most common findings:</strong>{" "}
      {stats.top_violations.map((item) => `${item.check} (${item.count})`).join(", ")}
    </div>}

    <div className="table-wrap"><table><thead><tr><th>Inspection</th><th>Captured</th><th>Category</th><th>Workflow</th><th>Decision</th></tr></thead><tbody>
      {scans.map((scan) => <tr key={scan.id}>
        <td><Link href={`/scans/${scan.id}`}><strong className="mono">{scan.id.slice(0, 8)}</strong></Link></td>
        <td>{new Date(scan.captured_at).toLocaleDateString("en-IN")}</td>
        <td>{scan.category}</td>
        <td><StatusPill value={scan.status} /></td>
        <td><StatusPill value={scan.overall} /></td>
      </tr>)}
    </tbody></table>{scans.length === 0 && <div className="empty">No products have been scanned into this investigation yet.</div>}</div>

    <div className="page-head"><div><h2>Notes</h2><p className="muted small">Append-only: a note keeps its author and time so a report can quote it.</p></div></div>
    {user?.permissions.includes("investigations:update") && <form className="toolbar" onSubmit={addNote}>
      <div className="field grow"><label htmlFor="note">Add a note</label><input id="note" className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What the photographs do not show" /></div>
      <button className="button primary" disabled={busy || !note.trim()}>Add note</button>
    </form>}
    {notes.length === 0 ? <div className="empty">No notes yet.</div> : notes.map((item) => <div key={item.id} className="notice">
      <div>{item.body}</div>
      <div className="muted small">{item.author || "Unknown"}{item.created_at ? ` · ${new Date(item.created_at).toLocaleString("en-IN")}` : ""}</div>
    </div>)}
  </AppShell>;
}
