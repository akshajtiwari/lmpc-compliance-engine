/* The signed-in session, as context rather than props.
 *
 * With a navigator between the root and every screen, `client` and `scope` can no
 * longer be prop-drilled without threading them through initialParams — which would put
 * a live API client into navigation state. */
import { createContext, useContext, useMemo, type ReactNode } from "react";

import { ApiClient } from "./api";
import { accountScope } from "./storage";
import type { AccountScope, Session } from "./types";

type Value = {
  session: Session;
  client: ApiClient;
  scope: AccountScope;
  setSession: (next: Session | null) => void;
};

const SessionContext = createContext<Value | null>(null);

export function SessionProvider({ session, setSession, children }: {
  session: Session;
  setSession: (next: Session | null) => void;
  children: ReactNode;
}) {
  const client = useMemo(
    () => new ApiClient(session, (next) => setSession(next)), [session, setSession]);
  const scope = useMemo(() => accountScope(session), [session]);
  const value = useMemo(
    () => ({ session, client, scope, setSession }), [session, client, scope, setSession]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Value {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession used outside a signed-in screen");
  return value;
}
