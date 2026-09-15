/* The root: open the device session, then hand over to the navigator.
 *
 * This file used to hold every screen, the styles and the navigation state in 162
 * deliberately dense lines. It could not absorb a folder list, a folder, and a report
 * screen on top of that, so those now live under src/screens and this is the shell. */
import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { RootNavigator } from "./src/navigation/RootNavigator";
import { EnrollmentScreen } from "./src/screens/EnrollScreen";
import { SessionProvider } from "./src/session";
import { loadSession, saveSession } from "./src/storage";
import { FatalScreen, Loading } from "./src/ui/primitives";
import type { Session } from "./src/types";

export default function App() {
  return <AppErrorBoundary><SafeAreaProvider><FieldApp /></SafeAreaProvider></AppErrorBoundary>;
}

class AppErrorBoundary extends Component<{children: ReactNode}, {error: Error | null}> {
  state: {error: Error | null} = {error: null};
  static getDerivedStateFromError(error: Error) { return {error}; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("LMPC Field render failed", error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return <FatalScreen message={this.state.error.message}
                          retry={() => this.setState({error: null})} />;
    }
    return this.props.children;
  }
}

function FieldApp() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [startupError, setStartupError] = useState("");

  useEffect(() => {
    let active = true;
    setReady(false);
    setStartupError("");
    loadSession()
      .then((stored) => { if (active) { setSession(stored); setReady(true); } })
      .catch((cause: unknown) => {
        if (!active) return;
        setStartupError(cause instanceof Error ? cause.message : "Device storage is unavailable");
        setReady(true);
      });
    return () => { active = false; };
  }, []);

  async function adopt(next: Session | null) {
    await saveSession(next);
    setSession(next);
  }

  if (!ready) return <Loading label="Opening encrypted device session…" />;
  if (startupError) {
    return <FatalScreen title="Could not open device storage" message={startupError}
                        retry={() => setReady(false)} />;
  }
  if (!session) return <><StatusBar style="light" /><EnrollmentScreen onComplete={adopt} /></>;

  return <SessionProvider session={session} setSession={(next) => { void adopt(next); }}>
    <StatusBar style="dark" />
    <RootNavigator />
  </SessionProvider>;
}
