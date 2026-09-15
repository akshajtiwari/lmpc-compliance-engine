/* One scan's report.
 *
 * Takes ids, not a result object, so it can be reopened, refreshed and restored after a
 * process kill. Renders the cached verdict first and revalidates behind it, which is what
 * makes a past report readable in a shop with no signal — the old screen did a blocking,
 * uncancellable fetch and showed an Alert when it failed. */
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";

import { isConnectionError } from "../api";
import { useSession } from "../session";
import { cacheScanResult, findInspection } from "../storage";
import { styles } from "../theme";
import { EmptyState, ErrorState, InlineSpinner } from "../ui/states";
import { Header, Outcome, RuleModal } from "../ui/primitives";
import type { LocalInspection, ReportSummary, RuleDetail, ScanResult } from "../types";
import type { RootParamList } from "../navigation/routes";

const MIME = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
} as const;

export function ScanReportScreen() {
  const navigation = useNavigation();
  const route = useRoute<RouteProp<RootParamList, "ScanReport">>();
  const {clientUuid, scanId} = route.params;
  const {client, scope} = useSession();

  const [row, setRow] = useState<LocalInspection | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [revalidating, setRevalidating] = useState(false);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async () => {
    const stored = await findInspection(clientUuid, scope);
    if (!alive.current) return;
    setRow(stored ?? null);
    if (stored?.result_json) {
      try { setResult(JSON.parse(stored.result_json) as ScanResult); } catch { /* refetch */ }
    }
    if (!scanId) return;
    setRevalidating(true);
    try {
      const fresh = await client.scan(scanId);
      if (!alive.current) return;
      setResult(fresh);
      setOffline(false);
      await cacheScanResult(clientUuid, scope, fresh);
      const list = await client.reports(scanId);
      if (alive.current) setReports(list.items);
    } catch (cause) {
      if (!alive.current) return;
      if (isConnectionError(cause)) setOffline(true);
      else setError(cause instanceof Error ? cause.message : "Could not refresh this report");
    } finally {
      if (alive.current) setRevalidating(false);
    }
  }, [clientUuid, scanId, client, scope]);

  useEffect(() => { queueMicrotask(() => { void load(); }); }, [load]);

  async function explain(check: string) {
    try { setRule(await client.rule(check)); }
    catch { setError("Rule explanations are not available on this server."); }
  }

  async function share(report: ReportSummary, format: "pdf" | "docx") {
    const key = `${report.id}:${format}`;
    setExporting(key); setError("");
    try {
      const Sharing = await import("expo-sharing");
      const file = await client.downloadReport(report.id, format);
      await Sharing.shareAsync(file.uri, {mimeType: MIME[format], UTI:
        format === "pdf" ? "com.adobe.pdf" : "org.openxmlformats.wordprocessingml.document"});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download that report");
    } finally { setExporting(null); }
  }

  const header = <Header title="Inspection" action="Back" onAction={navigation.goBack} />;

  if (!row && !result) return <View style={styles.flex}>{header}
    <View style={{padding: 16}}><InlineSpinner label="Opening…" /></View></View>;

  if (!result) return <View style={styles.flex}>{header}
    <ScrollView contentContainerStyle={styles.page}>
      <EmptyState
        title={row?.state === "COMPLETE" ? "Report not on this phone yet" : "Not uploaded yet"}
        body={row?.state === "COMPLETE"
          ? "This inspection was analysed on another device. Connect to the server to fetch it."
          : "The photographs are saved here. The verdict arrives once this uploads to the server."} />
      {!!row?.error && <ErrorState message={row.error} retry={load} />}
    </ScrollView></View>;

  return <View style={styles.flex}>
    {header}
    {offline && <View style={styles.offlineBanner}>
      <Text style={styles.offlineText}>Showing the copy saved on this phone.</Text></View>}
    <ScrollView contentContainerStyle={styles.page}>
      <View style={styles.resultHero}>
        <Outcome value={result.overall ?? "PENDING"} />
        <Text style={styles.resultSummary}>{result.decision_explanation?.summary}</Text>
      </View>
      {revalidating && <InlineSpinner label="Checking for an update…" />}
      {!!error && <ErrorState message={error} />}

      <Text style={styles.eyebrow}>REPORT</Text>
      {reports.length === 0
        ? <EmptyState title="No finalised report yet"
            body="A reviewing officer finalises the report before it can be downloaded." />
        : reports.map((report) => <View key={report.id} style={styles.folderCard}>
            <Text style={styles.folderName}>Version {report.version}</Text>
            <Text style={styles.folderMeta}>{report.overall_status}</Text>
            <View style={{flexDirection: "row", gap: 10, marginTop: 8}}>
              {(["pdf", "docx"] as const).map((format) =>
                <Pressable key={format} onPress={() => share(report, format)}
                           disabled={exporting !== null} style={styles.statChip}>
                  {exporting === `${report.id}:${format}`
                    ? <ActivityIndicator size="small" color="#1e6647" />
                    : <Text style={styles.statChipText}>{format.toUpperCase()}</Text>}
                </Pressable>)}
            </View>
          </View>)}

      <Text style={styles.eyebrow}>FINDINGS</Text>
      {result.evaluations.map((item) => <View key={item.check} style={styles.checkRow}>
        <View style={{flex: 1}}>
          <Text style={styles.scanRowTitle}>{item.clause}</Text>
          <Text style={styles.scanRowMeta}>{item.reason}</Text>
        </View>
        <Outcome value={item.outcome} />
        <Pressable onPress={() => explain(item.check)}><Text style={styles.link}>i</Text></Pressable>
      </View>)}
    </ScrollView>
    <RuleModal rule={rule} close={() => setRule(null)} />
  </View>;
}
