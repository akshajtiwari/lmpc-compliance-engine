"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth-provider";

export default function LoginPage() {
  return <Suspense fallback={<div className="empty">Opening sign in…</div>}><LoginForm /></Suspense>;
}

function LoginForm() {
  const { login, user, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("admin@lmpc.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(params.get("next") || "/dashboard");
  }, [ready, user, router, params]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await login(email, password);
      router.replace(params.get("next") || "/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed");
    } finally { setBusy(false); }
  }

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="brand"><div className="brand-mark">LM</div><div><div className="brand-title">LMPC Workbench</div><div className="brand-subtitle" style={{color: "var(--muted)"}}>On-premises inspection operations</div></div></div>
        <h1>Sign in</h1>
        <p className="muted" style={{marginTop: 0, marginBottom: 28}}>Use the administrator or reviewing-officer account configured on this server.</p>
        <form onSubmit={submit}>
          <div className="field"><label htmlFor="email">Email address</label><input className="input" id="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
          <div className="field"><label htmlFor="password">Password</label><input className="input" id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></div>
          {error && <div className="error" role="alert">{error}</div>}
          <button className="button primary" disabled={busy}>{busy ? "Checking…" : "Open workbench"}</button>
        </form>
      </section>
      <aside className="login-aside">
        <p className="eyebrow" style={{color: "#b8d2c1"}}>From evidence to an auditable finding</p>
        <h2>Inspect packages. Explain every rule. Preserve every decision.</h2>
        <p>The Workbench runs against your local LMPC server. Product photographs stay on this machine while field devices connect over the same trusted network.</p>
      </aside>
    </main>
  );
}
