"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { StatusPill } from "@/components/status-pill";
import type { Investigation } from "@/lib/types";

type Page = { items: Investigation[]; page: number; total: number; pages: number };

export default function InvestigationsPage() {
  const { api } = useAuth();
  const [result, setResult] = useState<Page | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "25", sort: "recent" });
    if (q) params.set("q", q); if (status) params.set("status", status);
    api<Page>(`/investigations?${params}`).then(setResult).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load investigations"));
  }, [api, page, q, status]);
  useEffect(load, [load]);
  function search(event: FormEvent) { event.preventDefault(); if (page === 1) load(); else setPage(1); }
  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Case files</p><h1>Investigations</h1><p>Every sweep, audit and complaint, with the products inspected under it. Officers open these on the Field app; this is the shared record.</p></div></div>
    <form className="toolbar" onSubmit={search}>
      <div className="field grow"><label htmlFor="search">Search</label><input id="search" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, brand or place" /></div>
      <div className="field"><label htmlFor="status">Status</label><select id="status" className="select" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">All</option><option>OPEN</option><option>CLOSED</option></select></div>
      <button className="button secondary">Apply filters</button>
    </form>
    {error && <div className="error">{error}</div>}
    <div className="table-wrap"><table><thead><tr><th>Investigation</th><th>Subject</th><th>Place</th><th>Products</th><th>Status</th></tr></thead><tbody>
      {result?.items.map((row) => <tr key={row.id}>
        <td><Link href={`/investigations/${row.id}`}><strong>{row.name}</strong><div className="muted small">{row.investigation_type.replaceAll("_", " ").toLowerCase()}</div></Link></td>
        <td>{row.subject_brand || <span className="muted">—</span>}</td>
        <td>{row.location_text || <span className="muted">—</span>}</td>
        <td>{row.scan_count ?? 0}{(row.failed_count ?? 0) > 0 && <div className="muted small">{row.failed_count} non-compliant</div>}</td>
        <td><StatusPill value={row.status} /></td>
      </tr>)}
    </tbody></table>{result && result.items.length === 0 && <div className="empty">No investigations match these filters.</div>}</div>
    {result && result.pages > 1 && <div className="toolbar"><button className="button secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span className="muted small">Page {result.page} of {result.pages}</span><button className="button secondary" disabled={page >= result.pages} onClick={() => setPage(page + 1)}>Next</button></div>}
  </AppShell>;
}
