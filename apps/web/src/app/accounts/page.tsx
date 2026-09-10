"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { StatusPill } from "@/components/status-pill";
import type { Enrollment, UserAccount } from "@/lib/types";

type Jurisdiction = { id: string; name: string; state: string; path: string };
const ROLES = ["FIELD_OFFICER", "REVIEWING_OFFICER", "AUDITOR", "ADMIN"];

export default function AccountsPage() {
  const { api, user: principal } = useAuth();
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [serverUrl, setServerUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canManage = principal?.permissions.includes("users:manage") ?? false;
  const load = useCallback(() => Promise.all([
    api<{items: UserAccount[]}>("/admin/users"), api<{items: Jurisdiction[]}>("/admin/jurisdictions"),
    api<{public_base_url:string}>("/version"),
  ]).then(([u,j,version]) => {setUsers(u.items); setJurisdictions(j.items); setServerUrl((current) => current || version.public_base_url);}), [api]);
  useEffect(() => { load().catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load accounts")); }, [load]);

  async function invite(account: UserAccount) {
    setBusy(true); setError("");
    try {
      const hostname = window.location.hostname;
      if (!serverUrl.trim() && (hostname === "localhost" || hostname === "127.0.0.1")) {
        throw new Error("Enter the computer's LAN server address, or restart the API with make dev-lan.");
      }
      const advertised = serverUrl.trim() || `${window.location.protocol}//${hostname}:8000`;
      setEnrollment(await api<Enrollment>(`/admin/users/${account.id}/enrollments`, {method: "POST", body: JSON.stringify({server_url: advertised})}));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not issue invitation"); }
    finally { setBusy(false); }
  }

  async function toggle(account: UserAccount) {
    setBusy(true); setError("");
    try { await api(`/admin/users/${account.id}`, {method: "PATCH", body: JSON.stringify({is_active: !account.is_active})}); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update account"); }
    finally { setBusy(false); }
  }

  return <AppShell>
    <div className="page-head"><div><p className="eyebrow">Access control</p><h1>Accounts & field devices</h1><p>Create officer identities here, then enroll the Field app using a short-lived one-time QR code.</p></div>{canManage && <button className="button primary" onClick={() => setCreateOpen(true)}>Create account</button>}</div>
    <div className="notice" style={{marginBottom:18}}><strong>Recommended connection:</strong> put the phone and server on the same network, then scan an enrollment QR. The QR carries the LAN address, server fingerprint and a token that expires in 15 minutes and works once.</div>
    {canManage && <div className="toolbar"><div className="field grow"><label htmlFor="server-url">LAN server address used in new QR codes</label><input id="server-url" className="input mono" value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} placeholder="Auto: http://this-computer:8000" /></div></div>}
    {error && <div className="error" style={{marginBottom:14}}>{error}</div>}
    <div className="table-wrap"><table><thead><tr><th>Officer</th><th>Role</th><th>Jurisdiction</th><th>State</th><th>Device access</th></tr></thead><tbody>{users.map((account) => <tr key={account.id}><td><strong>{account.full_name}</strong><div className="muted small">{account.email}</div></td><td>{account.role.replaceAll("_", " ")}</td><td className="mono small">{jurisdictions.find((j) => j.id === account.jurisdiction_id)?.name || "All / unassigned"}</td><td><StatusPill value={account.is_active ? "ACTIVE" : "INACTIVE"} /></td><td>{canManage ? <div style={{display:"flex",gap:7,flexWrap:"wrap"}}><button className="button secondary small" disabled={busy || !account.is_active} onClick={() => invite(account)}>Show enrollment QR</button><button className={`button small ${account.is_active ? "danger" : "secondary"}`} disabled={busy || account.id === principal?.id} onClick={() => toggle(account)}>{account.is_active ? "Deactivate" : "Activate"}</button></div> : <span className="muted small">Read only</span>}</td></tr>)}</tbody></table>{users.length === 0 && <div className="empty">No managed accounts yet.</div>}</div>
    {createOpen && <CreateAccount jurisdictions={jurisdictions} close={() => setCreateOpen(false)} created={async () => {setCreateOpen(false); await load();}} api={api} />}
    {enrollment && <EnrollmentDrawer enrollment={enrollment} close={() => setEnrollment(null)} />}
  </AppShell>;
}

function CreateAccount({jurisdictions, close, created, api}: {jurisdictions: Jurisdiction[]; close: () => void; created: () => Promise<void>; api: ReturnType<typeof useAuth>["api"]}) {
  const [form, setForm] = useState({full_name:"",email:"",role:"FIELD_OFFICER",jurisdiction_id:"",department:"Legal Metrology",password:""});
  const [error,setError] = useState(""); const [busy,setBusy] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await api("/admin/users", {method:"POST",body:JSON.stringify({...form,jurisdiction_id:form.jurisdiction_id || null,password:form.password || null})}); await created(); } catch(cause) {setError(cause instanceof Error ? cause.message : "Could not create account");} finally {setBusy(false);} }
  return <div className="drawer-backdrop" onMouseDown={close}><section className="drawer" onMouseDown={(e) => e.stopPropagation()}><div className="page-head"><div><p className="eyebrow">Managed identity</p><h2>Create account</h2></div><button className="button secondary small" onClick={close}>Close</button></div><form className="grid" onSubmit={submit}><Field label="Full name"><input className="input" value={form.full_name} onChange={(e)=>setForm({...form,full_name:e.target.value})} required /></Field><Field label="Email"><input className="input" type="email" value={form.email} onChange={(e)=>setForm({...form,email:e.target.value})} required /></Field><Field label="Role"><select className="select" value={form.role} onChange={(e)=>setForm({...form,role:e.target.value})}>{ROLES.map(role=><option key={role}>{role}</option>)}</select></Field><Field label="Jurisdiction"><select className="select" value={form.jurisdiction_id} onChange={(e)=>setForm({...form,jurisdiction_id:e.target.value})}><option value="">Unassigned / all for administrators</option>{jurisdictions.map(j=><option key={j.id} value={j.id}>{j.state} · {j.name}</option>)}</select></Field><Field label="Department"><input className="input" value={form.department} onChange={(e)=>setForm({...form,department:e.target.value})} /></Field><Field label="Optional web password"><input className="input" type="password" minLength={12} value={form.password} onChange={(e)=>setForm({...form,password:e.target.value})} placeholder="Leave blank for QR-only field access" /></Field>{error && <div className="error">{error}</div>}<button className="button primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button></form></section></div>;
}

function EnrollmentDrawer({enrollment,close}:{enrollment:Enrollment;close:()=>void}) {
  return <div className="drawer-backdrop" onMouseDown={close}><section className="drawer" onMouseDown={(e)=>e.stopPropagation()}><div className="page-head"><div><p className="eyebrow">One-time field enrollment</p><h2>{enrollment.user.full_name}</h2></div><button className="button secondary small" onClick={close}>Close</button></div><div className="qr-card"><QRCodeSVG value={enrollment.enrollment_uri} size={250} level="M" includeMargin /><strong>Scan in LMPC Field</strong><span className="muted small">Expires {new Date(enrollment.expires_at).toLocaleString("en-IN")}</span></div><div className="drawer-section"><h3>Server</h3><p className="mono small">{enrollment.server_url}</p></div><div className="drawer-section"><h3>Fingerprint to compare</h3><p className="mono small" style={{overflowWrap:"anywhere"}}>{enrollment.server_fingerprint}</p></div><div className="notice">Do not send a screenshot over public chat. Close this invitation after the officer&apos;s phone confirms enrollment; it cannot be used again.</div></section></div>;
}
function Field({label,children}:{label:string;children:React.ReactNode}) { return <div className="field"><label>{label}</label>{children}</div>; }
