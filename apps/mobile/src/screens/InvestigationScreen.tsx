/* One investigation: the folder an officer works inside.
 *
 * Header, running totals, notes, and every scan filed under it — newest first, and
 * readable with no network because each result is cached when it arrives. */
import { useCallback, useState } from "react";
import { Alert, FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useFocusEffect, useNavigation, useRoute, type RouteProp } from "@react-navigation/native";

import { useSession } from "../session";
import { summarise } from "../investigations";
import { getInvestigation, investigationScans } from "../storage";
import { styles } from "../theme";
import { EmptyState, ErrorState, ListSkeleton } from "../ui/states";
import { Header, Outcome, Primary } from "../ui/primitives";
import type { LocalInspection, LocalInvestigation, RootParamList } from "../types";

export function InvestigationScreen() {
  const navigation = useNavigation();
  const route = useRoute<RouteProp<RootParamList, "Investigation">>();
  const {investigationId} = route.params;
  const {scope} = useSession();
  const [folder, setFolder] = useState<LocalInvestigation | null>(null);
  const [rows, setRows] = useState<LocalInspection[] | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [found, scans] = await Promise.all([
        getInvestigation(investigationId, scope),
        investigationScans(investigationId, scope),
      ]);
      setFolder(found ?? null);
      setRows(scans);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open this investigation");
    }
  }, [investigationId, scope]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  function newScan() {
    if (folder?.status === "CLOSED") {
      Alert.alert("This investigation is closed", "Reopen it before adding another scan.");
      return;
    }
    Alert.alert("New scan", "What are you inspecting?", [
      {text: "A physical package",
       onPress: () => navigation.navigate("Capture", {investigationId})},
      {text: "An online listing",
       onPress: () => navigation.navigate("ListingCapture", {investigationId})},
      {text: "Cancel", style: "cancel"},
    ]);
  }

  if (error) return <View style={styles.flex}>
    <Header title="Investigation" action="Back" onAction={navigation.goBack} />
    <View style={{padding: 16}}><ErrorState message={error} retry={load} /></View>
  </View>;

  if (!folder || rows === null) return <View style={styles.flex}>
    <Header title="Investigation" action="Back" onAction={navigation.goBack} />
    <View style={{padding: 16}}><ListSkeleton /></View>
  </View>;

  const stats = summarise(rows);
  const place = [folder.subject_brand, folder.location_text].filter(Boolean).join(" · ");

  return <View style={styles.flex}>
    <Header title={folder.name} action="Back" onAction={navigation.goBack} />
    <FlatList
      data={rows}
      keyExtractor={(row) => row.client_uuid}
      contentContainerStyle={{padding: 16, gap: 10, paddingBottom: 100}}
      refreshControl={<RefreshControl refreshing={refreshing}
        onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      ListHeaderComponent={
        <View style={{gap: 12, marginBottom: 4}}>
          <View style={styles.folderCard}>
            <Text style={styles.folderName}>{folder.name}</Text>
            {!!place && <Text style={styles.folderMeta}>{place}</Text>}
            <Text style={styles.folderMeta}>
              {folder.investigation_type.replaceAll("_", " ").toLowerCase()}
              {folder.status === "CLOSED" ? " · closed" : ""}
              {folder.server_id ? "" : " · not yet uploaded"}
            </Text>
            <View style={styles.statStrip}>
              <Stat label={`${stats.total} scan${stats.total === 1 ? "" : "s"}`} />
              {stats.compliant > 0 && <Stat label={`${stats.compliant} compliant`} />}
              {stats.failing > 0 && <Stat label={`${stats.failing} non-compliant`} />}
              {stats.unclear > 0 && <Stat label={`${stats.unclear} unclear`} />}
              {stats.pending > 0 && <Stat label={`${stats.pending} waiting`} />}
            </View>
          </View>
          {stats.topViolations.length > 0 && <View style={styles.folderCard}>
            <Text style={styles.folderName}>Most common findings</Text>
            {stats.topViolations.map((item) =>
              <Text key={item.check} style={styles.folderMeta}>
                {item.count}× {item.check}</Text>)}
            <Text style={styles.noteMeta}>
              From {stats.withReports} of {stats.total} reports held on this phone.
            </Text>
          </View>}
        </View>}
      ListEmptyComponent={
        <EmptyState title="No scans yet"
                    body="Scan the first product into this investigation. Each report is saved here and stays readable without a connection."
                    action="New scan" onAction={newScan} />}
      renderItem={({item}) => <ScanRow row={item}
        onPress={() => navigation.navigate("ScanReport",
          {clientUuid: item.client_uuid, scanId: item.scan_id})} />} />

    <View style={{position: "absolute", left: 16, right: 16, bottom: 18}}>
      <Primary label="New scan" onPress={newScan} />
    </View>
  </View>;
}

function Stat({label}: {label: string}) {
  return <View style={styles.statChip}><Text style={styles.statChipText}>{label}</Text></View>;
}

function ScanRow({row, onPress}: {row: LocalInspection; onPress: () => void}) {
  const when = new Date(row.captured_ts ?? row.updated_at);
  const state = row.state === "COMPLETE" ? null
    : row.state === "FAILED" ? "Upload failed — will retry"
    : row.state === "UPLOADING" ? "Uploading…" : "Waiting to upload";
  return <Pressable onPress={onPress} style={styles.scanRow}>
    <View style={{flex: 1}}>
      <Text style={styles.scanRowTitle}>{row.category.replaceAll("_", " ")}</Text>
      <Text style={styles.scanRowMeta}>
        {when.toLocaleString()}{state ? ` · ${state}` : ""}
        {row.remarks ? " · note" : ""}
      </Text>
    </View>
    {row.overall ? <Outcome value={row.overall} /> : null}
  </Pressable>;
}
