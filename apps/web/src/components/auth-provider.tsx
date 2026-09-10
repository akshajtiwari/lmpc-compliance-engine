"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { Principal } from "@/lib/types";

type ApiOptions = RequestInit & { retryAuth?: boolean };
type AuthValue = {
  user: Principal | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  api: <T>(path: string, options?: ApiOptions) => Promise<T>;
  download: (path: string) => Promise<Blob>;
};

const AuthContext = createContext<AuthValue | null>(null);

async function messageOf(response: Response): Promise<string> {
  try {
    const body = await response.json() as { error?: { message?: string } };
    return body.error?.message ?? `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Principal | null>(null);
  const [ready, setReady] = useState(false);
  const access = useRef<string | null>(null);
  const refreshing = useRef<Promise<boolean> | null>(null);

  const refresh = useCallback(async () => {
    if (refreshing.current) return refreshing.current;
    refreshing.current = (async () => {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      if (!response.ok) {
        access.current = null;
        setUser(null);
        return false;
      }
      const body = await response.json() as { access_token: string; user: Principal };
      access.current = body.access_token;
      setUser(body.user);
      return true;
    })().finally(() => { refreshing.current = null; });
    return refreshing.current;
  }, []);

  useEffect(() => {
    refresh().catch(() => false).finally(() => setReady(true));
  }, [refresh]);

  const api = useCallback(async <T,>(path: string, options: ApiOptions = {}): Promise<T> => {
    const { retryAuth = true, ...requestOptions } = options;
    const headers = new Headers(requestOptions.headers);
    if (access.current) headers.set("Authorization", `Bearer ${access.current}`);
    if (requestOptions.body && !(requestOptions.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    let response = await fetch(`/api/v1${path}`, { ...requestOptions, headers, credentials: "include" });
    if (response.status === 401 && retryAuth && await refresh()) {
      headers.set("Authorization", `Bearer ${access.current}`);
      response = await fetch(`/api/v1${path}`, { ...requestOptions, headers, credentials: "include" });
    }
    if (!response.ok) throw new Error(await messageOf(response));
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error(await messageOf(response));
    const body = await response.json() as { access_token: string; user: Principal };
    access.current = body.access_token;
    setUser(body.user);
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" }).catch(() => undefined);
    access.current = null;
    setUser(null);
  }, []);

  const download = useCallback(async (path: string) => {
    const headers = new Headers();
    if (access.current) headers.set("Authorization", `Bearer ${access.current}`);
    let response = await fetch(`/api/v1${path}`, { headers, credentials: "include" });
    if (response.status === 401 && await refresh()) {
      headers.set("Authorization", `Bearer ${access.current}`);
      response = await fetch(`/api/v1${path}`, { headers, credentials: "include" });
    }
    if (!response.ok) throw new Error(await messageOf(response));
    return response.blob();
  }, [refresh]);

  const value = useMemo(() => ({ user, ready, login, logout, api, download }), [user, ready, login, logout, api, download]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
