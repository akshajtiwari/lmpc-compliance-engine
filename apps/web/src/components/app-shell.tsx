"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "./auth-provider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [ready, user, router, pathname]);

  if (!ready || !user) return <div className="empty">Opening secure workbench…</div>;
  const links = [
    ["/dashboard", "Overview", "⌂"],
    ["/scans", "Inspections", "▦"],
    ...(user.permissions.includes("users:read") ? [["/accounts", "Accounts", "◎"]] : []),
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">LM</div>
          <div className="brand-copy"><div className="brand-title">LMPC Workbench</div><div className="brand-subtitle">Local enforcement system</div></div>
        </div>
        <nav className="nav" aria-label="Primary">
          {links.map(([href, label, icon]) => (
            <Link key={href} className={`nav-link ${pathname.startsWith(href) ? "active" : ""}`} href={href}>
              <span aria-hidden>{icon}</span> <span className="nav-label">{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-user">
          <strong>{user.full_name}</strong><small>{user.role.replaceAll("_", " ")}</small>
          <button className="button text" onClick={async () => { await logout(); router.replace("/login"); }}>Sign out</button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar"><span className="topbar-kicker">Legal Metrology · Packaged Commodities</span><span className="small muted">Local server</span></header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
