"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import type { RuleDetail } from "@/lib/types";

export default function RulePage() {
  const { check } = useParams<{ check: string }>();
  const { api } = useAuth();
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api<RuleDetail>(`/rules/${encodeURIComponent(check)}`).then(setRule)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load this rule"));
  }, [api, check]);
  useEffect(load, [load]);
  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Rule management</p><h1 className="mono">{check}</h1>
      <p>{rule?.title ?? "Reading the rulepack…"}</p></div><Link href="/rules" className="button secondary">All checks</Link></div>
    {error && <div className="error" role="alert">{error}</div>}
    {rule && <>
      <section className="card" aria-label="Requirement">
        <h2>Requirement</h2>
        <p>{rule.requirement}</p>
        <p className="muted small">Clause {rule.clause}{rule.effective_from ? ` · in force from ${rule.effective_from}` : ""}{rule.authority.gsr ? ` · ${rule.authority.gsr}` : ""}{rule.authority.page ? `, p. ${rule.authority.page}` : ""}</p>
      </section>
      <section className="card" aria-label="How it is judged">
        <h2>How the engine judges it</h2>
        <p>{rule.method}</p>
        <h3 style={{marginTop: 15}}>Evidence needed</h3>
        <p>{rule.evidence_needed}</p>
        {rule.important_limits.length > 0 && <>
          <h3 style={{marginTop: 15}}>Limits of this check</h3>
          <ul>{rule.important_limits.map((limit) => <li key={limit}>{limit}</li>)}</ul>
        </>}
      </section>
      <section className="card" aria-label="Outcomes">
        <h2>What each outcome means</h2>
        {Object.entries(rule.outcomes).map(([outcome, meaning]) => <div key={outcome} style={{display: "flex", justifyContent: "space-between", padding: "10px 0", borderTop: "1px solid var(--line)", gap: 15}}><strong className="mono small">{outcome}</strong><span className="muted small">{meaning}</span></div>)}
        <p className="muted small" style={{marginTop: 15}}>{rule.non_normative_notice}</p>
      </section>
    </>}
  </AppShell>;
}