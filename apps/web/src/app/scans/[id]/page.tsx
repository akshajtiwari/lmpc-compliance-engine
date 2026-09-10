"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { StatusPill } from "@/components/status-pill";
import type { Declaration, Evaluation, RuleDetail, Scan } from "@/lib/types";

type Report = {id:string;version:number;overall_status:string;finalized_at:string;content_sha256:string};

export default function ScanDetailPage() {
  const id = useParams<{id:string}>().id;
  const { api, download, user } = useAuth();
  const [scan, setScan] = useState<Scan | null>(null);
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [override, setOverride] = useState<Evaluation | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => Promise.all([
    api<Scan>(`/scans/${id}`), api<{items:Report[]}>(`/scans/${id}/reports`),
  ]).then(([scanValue,reportValue]) => {setScan(scanValue);setReports(reportValue.items);}), [api,id]);
  useEffect(() => { load().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load inspection")); }, [load]);
  const effective = useMemo(() => {
    const map = new Map<string,Evaluation>();
    for (const item of scan?.evaluations ?? []) map.set(item.check,item);
    return [...map.values()];
  }, [scan]);
  const sourceUrl = safeHttpUrl(scan?.ecommerce?.url ?? null);

  async function action(work: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await work(); await load(); } catch(cause) { setError(cause instanceof Error ? cause.message : "Action failed"); }
    finally { setBusy(false); }
  }
  async function showRule(check: string) {
    setError(""); try { setRule(await api<RuleDetail>(`/rules/${encodeURIComponent(check)}`)); }
    catch(cause) {setError(cause instanceof Error ? cause.message : "Could not load rule guidance");}
  }
  async function finalize() {
    await action(async () => { const result = await api<{report_id:string}>(`/scans/${id}/report`, {method:"POST"}); setReportId(result.report_id); });
  }
  async function saveFile(format: "pdf"|"docx") {
    const activeReport = reportId || reports[0]?.id;
    if (!activeReport) return; setBusy(true); setError("");
    try { const blob = await download(`/reports/${activeReport}/download?format=${format}`); const url = URL.createObjectURL(blob); const anchor=document.createElement("a"); anchor.href=url; anchor.download=`LMPC-${id.slice(0,8)}.${format}`; anchor.click(); URL.revokeObjectURL(url); }
    catch(cause){setError(cause instanceof Error ? cause.message : "Download failed");} finally{setBusy(false);}
  }

  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Inspection <span className="mono">{id.slice(0,8)}</span></p><h1>{scan?.category || "Loading inspection…"}</h1><p>{scan ? `${new Date(scan.captured_at).toLocaleString("en-IN")} · ${scan.mode.replaceAll("_"," ")} · ${scan.buyer_type} buyer` : "Retrieving evidence and findings"}</p></div><div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{scan && <StatusPill value={scan.overall || scan.status} />}{user?.permissions.includes("scans:reevaluate") && <button className="button secondary" disabled={busy} onClick={()=>action(()=>api(`/scans/${id}/reevaluate`,{method:"POST"}))}>Re-run evaluation</button>}{user?.permissions.includes("reports:create") && scan?.status !== "FINALIZED" && <button className="button primary" disabled={busy} onClick={finalize}>Finalise report</button>}</div></div>
    {error && <div className="error" style={{marginBottom:15}}>{error}</div>}
    {scan?.decision_explanation && <div className="notice" style={{marginBottom:18}}><strong>{scan.decision_explanation.heading}.</strong> {scan.decision_explanation.summary}<br/><span className="small"><strong>Next:</strong> {scan.decision_explanation.next_step}</span></div>}
    {(reportId || reports[0]) && <div className="card" style={{marginBottom:18,display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}><strong>Final report {reports[0]?.version ? `v${reports[0].version}` : "ready"}</strong><span className="muted small mono">{reportId || reports[0]?.id}</span><button className="button secondary small" onClick={()=>saveFile("pdf")}>Download PDF</button><button className="button secondary small" onClick={()=>saveFile("docx")}>Download editable DOCX</button></div>}
    <div className="grid two-col">
      <div className="grid">
        {scan?.ecommerce && <section className="card"><h2>Listing source</h2>
          {sourceUrl && <p><a className="source-link" href={sourceUrl}
            target="_blank" rel="noreferrer">Open captured product page ↗</a></p>}
          <pre className="listing-text">{scan.ecommerce.listing_text}</pre>
        </section>}
        <section className="card"><h2>Evidence</h2><div className="evidence-grid">{scan?.images.map((item)=><EvidenceImage key={item.panel} panel={item.panel} path={item.url.replace("/api/v1","")} download={download} />)}</div>{scan && !scan.images.length && <div className="empty">No evidence images.</div>}</section>
        <section className="card"><h2>Extracted declarations</h2><p className="muted small">Corrections are append-only and require a fresh rule evaluation.</p>{scan?.declarations.map((item)=><DeclarationEditor key={item.id} declaration={item} disabled={busy || scan.status === "FINALIZED"} save={(text)=>action(()=>api(`/scans/${id}/declarations/${item.field}`,{method:"POST",body:JSON.stringify({text})}))} />)}{scan && !scan.declarations.length && <div className="empty">No declarations were established from this evidence.</div>}</section>
      </div>
      <section className="card"><h2>Rule findings</h2><p className="muted small">Use the <strong>i</strong> button on every finding to see what the rule means, how this result was produced, and what evidence is needed.</p><div className="rule-list">{effective.map((item)=><article className="rule-card" key={item.check}><div className="rule-card-head"><div><h3>{item.clause}</h3><StatusPill value={item.outcome} /></div><button className="info-button" aria-label={`Explain ${item.clause}`} title="Explain this rule" onClick={()=>showRule(item.check)}>i</button></div><p>{item.reason}</p>{item.is_override && <p className="mono">Officer override</p>}{user?.permissions.includes("evaluations:override") && scan?.status !== "FINALIZED" && <button className="button text small" onClick={()=>setOverride(item)}>Record reasoned override</button>}</article>)}{scan && !effective.length && <div className="empty">Evaluation has not completed.</div>}</div></section>
    </div>
    {rule && <RuleDrawer rule={rule} close={()=>setRule(null)} />}
    {override && <OverrideDrawer evaluation={override} close={()=>setOverride(null)} save={(outcome,reason)=>action(async()=>{await api(`/scans/${id}/evaluations/${override.id}/override`,{method:"POST",body:JSON.stringify({outcome,reason})});setOverride(null);})} />}
  </AppShell>;
}

function safeHttpUrl(value: string | null) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    const isHttp = parsed.protocol === "http:" || parsed.protocol === "https:";
    return isHttp && !parsed.username && !parsed.password ? value : null;
  } catch {
    return null;
  }
}

function EvidenceImage({panel,path,download}:{panel:string;path:string;download:(path:string)=>Promise<Blob>}) {
  const [src,setSrc]=useState("");
  useEffect(()=>{let url="";download(path).then(blob=>{url=URL.createObjectURL(blob);setSrc(url);}).catch(()=>setSrc(""));return()=>{if(url)URL.revokeObjectURL(url);};},[download,path]);
  return <figure className="evidence">{src ? <Image src={src} alt={`${panel} package panel`} width={1000} height={800} unoptimized /> : <div className="empty">Loading {panel}…</div>}<figcaption>{panel}</figcaption></figure>;
}

function DeclarationEditor({declaration,disabled,save}:{declaration:Declaration;disabled:boolean;save:(text:string)=>Promise<void>}) {
  const [text,setText]=useState(declaration.text); const changed=text.trim()!==declaration.text;
  return <div className="declaration"><div><strong>{declaration.field.replaceAll("_"," ")}</strong><div className="muted small">{declaration.panel} · {Math.round((declaration.confidence ?? 0)*100)}%</div></div><input className="input" value={text} disabled={disabled} onChange={(e)=>setText(e.target.value)} /><button className="button secondary small" disabled={disabled||!changed||!text.trim()} onClick={()=>save(text)}>Correct</button></div>;
}

function RuleDrawer({rule,close}:{rule:RuleDetail;close:()=>void}) { return <div className="drawer-backdrop" onMouseDown={close}><section className="drawer" onMouseDown={e=>e.stopPropagation()}><div className="page-head"><div><p className="eyebrow">{rule.clause}</p><h2>{rule.title}</h2></div><button className="button secondary small" onClick={close}>Close</button></div><div className="drawer-section"><h3>What the requirement is</h3><p>{rule.requirement}</p></div><div className="drawer-section"><h3>What the system did</h3><p>{rule.method}</p></div><div className="drawer-section"><h3>Evidence needed</h3><p>{rule.evidence_needed}</p></div>{rule.important_limits.length>0&&<div className="drawer-section"><h3>Important limits</h3><ul>{rule.important_limits.map(item=><li key={item}>{item}</li>)}</ul></div>}<div className="drawer-section"><h3>Why outcomes differ</h3>{Object.entries(rule.outcomes).map(([key,value])=><p key={key}><StatusPill value={key} /> <span className="small">{value}</span></p>)}</div><div className="notice">{rule.non_normative_notice}</div></section></div>; }

function OverrideDrawer({evaluation,close,save}:{evaluation:Evaluation;close:()=>void;save:(outcome:string,reason:string)=>Promise<void>}) {
  const [outcome,setOutcome]=useState(evaluation.outcome);const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{await save(outcome,reason);}catch(cause){setError(cause instanceof Error?cause.message:"Override failed");}finally{setBusy(false);}}
  return <div className="drawer-backdrop" onMouseDown={close}><section className="drawer" onMouseDown={e=>e.stopPropagation()}><div className="page-head"><div><p className="eyebrow">Reasoned officer action</p><h2>Override {evaluation.clause}</h2></div><button className="button secondary small" onClick={close}>Close</button></div><form className="grid" onSubmit={submit}><div className="notice">Current outcome: <strong>{evaluation.outcome.replaceAll("_"," ")}</strong>. Overrides remain in the audit history.</div><div className="field"><label>New outcome</label><select className="select" value={outcome} onChange={e=>setOutcome(e.target.value)}>{["PASS","FAIL","INDETERMINATE","NOT_APPLICABLE","REVIEW_REQUIRED"].map(x=><option key={x}>{x}</option>)}</select></div><div className="field"><label>Reason (at least 10 characters)</label><textarea className="textarea" value={reason} onChange={e=>setReason(e.target.value)} required minLength={10} /></div>{error&&<div className="error">{error}</div>}<button className="button primary" disabled={busy||reason.trim().length<10}>{busy?"Saving…":"Record override"}</button></form></section></div>;
}
