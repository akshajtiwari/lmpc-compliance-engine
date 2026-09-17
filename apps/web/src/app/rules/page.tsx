"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import type { RulepackOverview } from "@/lib/types";

function cite(authority: { gsr?: string; dated?: string; page?: number }) {
  const parts = [authority.gsr, authority.dated, authority.page ? `p. ${authority.page}` : ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export default function RulesPage() {
  const { api } = useAuth();
  const [pack, setPack] = useState<RulepackOverview | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api<RulepackOverview>("/rules").then(setPack).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load the rulepack"));
  }, [api]);
  useEffect(load, [load]);
  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Rule management</p><h1>The compiled rulepack</h1>
      <p>The law in force, compiled once from the gazettes into a hashed, versioned pack. Every verdict cites an entry below; this is the surface to confirm what the engine is applying.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {pack && <>
      <section className="grid metrics" aria-label="Rulepack identity">
        <div className="card"><div className="metric-label">Rulepack</div><div className="metric-value mono small">{pack.rulepack.version}</div><div className="metric-note">compiled {new Date(pack.rulepack.built_at).toLocaleDateString()}</div></div>
        <div className="card"><div className="metric-label">SHA-256</div><div className="metric-value mono small">{pack.rulepack.sha256.slice(0, 12)}…</div><div className="metric-note">the hash stamped into every report</div></div>
        <div className="card"><div className="metric-label">Coverage</div><div className="metric-value">{pack.rulepack.check_count} checks</div><div className="metric-note">{pack.rulepack.gate_count} applicability gates</div></div>
      </section>
      {pack.rulepack.unverified_bindings > 0 && <div className="error" role="alert">{pack.rulepack.unverified_bindings} instrument bindings in this rulepack remain unverified against the gazette — they are recorded in the compiled JSON, not silently dropped.</div>}
      <section className="card" aria-label="Applicability gates">
        <h2>Applicability gates</h2>
        <p className="muted small">Decided before any check runs: whether the package is even within scope of these rules.</p>
        <div className="table-wrap"><table><thead><tr><th>Gate</th><th>Clause</th><th>Authority</th></tr></thead><tbody>
          {pack.gates.map((gate) => <tr key={gate.gate}>
            <td><strong className="mono small">{gate.gate}</strong></td>
            <td>{gate.clause}</td>
            <td className="muted small">{cite(gate.authority)}</td>
          </tr>)}
        </tbody></table></div>
      </section>
      <section className="card" aria-label="Checks">
        <h2>Checks</h2>
        <div className="table-wrap"><table><thead><tr><th>Check</th><th>Requirement</th><th>Clause</th><th>Operator</th><th>In force from</th></tr></thead><tbody>
          {pack.checks.map((check) => <tr key={check.check}>
            <td><Link href={`/rules/${check.check}`}><strong className="mono small">{check.check}</strong><div className="muted small">{check.title}</div></Link></td>
            <td>{check.requirement}</td>
            <td>{check.clause}<div className="muted small">{cite(check.authority)}</div></td>
            <td><code className="mono small">{check.operator ?? "—"}</code></td>
            <td>{check.effective_from || <span className="muted">—</span>}</td>
          </tr>)}
        </tbody></table></div>
      </section>
    </>}
  </AppShell>;
}