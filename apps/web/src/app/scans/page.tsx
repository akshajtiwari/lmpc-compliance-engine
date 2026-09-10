"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { StatusPill } from "@/components/status-pill";
import type { ScanSummary } from "@/lib/types";

type Page = { items: ScanSummary[]; page: number; page_size: number; total: number; pages: number };

export default function ScansPage() {
  const { api, user } = useAuth();
  const [result, setResult] = useState<Page | null>(null);
  const [q, setQ] = useState("");
  const [overall, setOverall] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "25", sort: "newest" });
    if (q) params.set("q", q); if (overall) params.set("overall", overall);
    api<Page>(`/scans?${params}`).then(setResult).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load inspections"));
  }, [api, page, q, overall]);
  useEffect(load, [load]);
  function search(event: FormEvent) { event.preventDefault(); if (page === 1) load(); else setPage(1); }
  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Repository</p><h1>Inspections</h1><p>Search product evidence, evaluation status and compliance history.</p></div>{user?.permissions.includes("scans:create") && <Link className="button primary" href="/scans/new">New inspection</Link>}</div>
    <form className="toolbar" onSubmit={search}><div className="field grow"><label htmlFor="search">Search</label><input id="search" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Manufacturer, brand or inspection UUID" /></div><div className="field"><label htmlFor="overall">Decision</label><select id="overall" className="select" value={overall} onChange={(e) => {setOverall(e.target.value); setPage(1);}}><option value="">All decisions</option>{["COMPLIANT","NON_COMPLIANT","REVIEW_REQUIRED","INCOMPLETE_EVIDENCE","OUT_OF_SCOPE","SYSTEM_ERROR"].map(x => <option key={x}>{x}</option>)}</select></div><button className="button secondary">Apply filters</button></form>
    {error && <div className="error">{error}</div>}
    <div className="table-wrap"><table><thead><tr><th>Inspection</th><th>Product</th><th>Captured</th><th>Workflow</th><th>Decision</th></tr></thead><tbody>{result?.items.map((scan) => <tr key={scan.id}><td><Link href={`/scans/${scan.id}`}><strong className="mono">{scan.id.slice(0,8)}</strong><div className="muted small">{scan.mode.replaceAll("_", " ")}</div></Link></td><td><strong>{scan.brand || scan.manufacturer || "Unlinked product"}</strong><div className="muted small">{scan.category}</div></td><td>{new Date(scan.captured_at).toLocaleDateString("en-IN")}<div className="muted small">{scan.coverage_asserted ? "Coverage confirmed" : "Partial evidence"}</div></td><td><StatusPill value={scan.status} /></td><td><StatusPill value={scan.overall} /></td></tr>)}</tbody></table>{result && result.items.length === 0 && <div className="empty">No inspections match these filters.</div>}</div>
    <div className="pager"><span className="muted small">{result?.total ?? 0} inspections · page {result?.page ?? page} of {Math.max(result?.pages ?? 1,1)}</span><div style={{display:"flex",gap:8}}><button className="button secondary small" disabled={page <= 1} onClick={() => setPage(v => v-1)}>Previous</button><button className="button secondary small" disabled={page >= (result?.pages ?? 1)} onClick={() => setPage(v => v+1)}>Next</button></div></div>
  </AppShell>;
}
