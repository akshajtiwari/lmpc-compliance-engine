"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";

type Summary = { today: number; last_7_days: number; total: number; pending_reviews: number; non_compliant: number; violation_rate: number };
type Quality = { scans: number; images: number; declarations_per_scan: number; abstention_rate: number; override_rate: number; false_accusation_guard_breaches: number };
type Violation = { check: string; clause: string; count: number };
type Maker = { manufacturer: string; count: number };

export default function DashboardPage() {
  const { api } = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [makers, setMakers] = useState<Maker[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<Summary>("/dashboard/summary"), api<Quality>("/dashboard/quality"),
      api<Violation[]>("/dashboard/violations-by-type?limit=8"), api<Maker[]>("/dashboard/top-non-compliant?limit=8"),
    ]).then(([a,b,c,d]) => { setSummary(a); setQuality(b); setViolations(c); setMakers(d); }).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load dashboard"));
  }, [api]);

  const maxViolation = Math.max(...violations.map((item) => item.count), 1);
  return (
    <AppShell>
      <div className="page-head"><div><p className="eyebrow">Operational overview</p><h1>Compliance dashboard</h1><p>Jurisdiction-scoped activity and quality signals from the local inspection repository.</p></div><Link href="/scans" className="button primary">Review inspections</Link></div>
      {error && <div className="error" role="alert">{error}</div>}
      <section className="grid metrics" aria-label="Inspection summary">
        <Metric label="Inspections today" value={summary?.today} note={`${summary?.last_7_days ?? "—"} in the last 7 days`} />
        <Metric label="Pending review" value={summary?.pending_reviews} note="Needs officer attention" />
        <Metric label="Non-compliant" value={summary?.non_compliant} note={`${Math.round((summary?.violation_rate ?? 0) * 100)}% of decided scans`} />
        <Metric label="Evidence images" value={quality?.images} note={`${quality?.declarations_per_scan ?? "—"} declarations / scan`} />
      </section>
      <section className="grid two-col" style={{marginTop: 18}}>
        <div className="card"><h2>Most frequent failed checks</h2><p className="muted small">Only evidence-backed FAIL outcomes are counted.</p>{violations.length ? violations.map((item) => <div className="bar-row" key={item.check}><span title={item.check}>{item.clause}</span><div className="bar-track"><div className="bar-fill" style={{width: `${item.count / maxViolation * 100}%`}} /></div><strong className="mono">{item.count}</strong></div>) : <div className="empty">No violations recorded yet.</div>}</div>
        <div className="card"><h2>Quality guardrails</h2><QualityLine label="Abstention rate" value={quality ? `${Math.round(quality.abstention_rate * 100)}%` : "—"} /><QualityLine label="Officer override rate" value={quality ? `${Math.round(quality.override_rate * 100)}%` : "—"} /><QualityLine label="Unsafe absence calls" value={quality?.false_accusation_guard_breaches ?? "—"} /><h3 style={{marginTop: 25}}>Top non-compliant manufacturers</h3>{makers.length ? makers.map((item) => <QualityLine key={item.manufacturer} label={item.manufacturer} value={item.count} />) : <p className="muted small">No manufacturer data yet.</p>}</div>
      </section>
    </AppShell>
  );
}

function Metric({label, value, note}: {label: string; value?: number; note: string}) { return <div className="card"><div className="metric-label">{label}</div><div className="metric-value">{value ?? "—"}</div><div className="metric-note">{note}</div></div>; }
function QualityLine({label, value}: {label: string; value: string | number}) { return <div style={{display: "flex", justifyContent: "space-between", padding: "10px 0", borderTop: "1px solid var(--line)", gap: 15}}><span className="muted small">{label}</span><strong className="mono small">{value}</strong></div>; }
