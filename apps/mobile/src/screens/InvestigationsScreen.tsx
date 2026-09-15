/* The root screen: every investigation this officer can open.
 *
 * Replaces the old flat "recent inspections" list, which showed 30 device-local rows in a
 * ScrollView and had no way of saying which sweep a scan belonged to. */
import { useCallback, useEffect, useState } from "react";
import { AppState, FlatList, Pressable, RefreshControl, Text, TextInput, View } from "react-native";
import NetInfo from "@react-native-community/netinfo";
import { useFocusEffect, useNavigation } from "@react-navigation/native";

import { isConnectionError } from "../api";
import { useSession } from "../session";
import { sweep } from "../cleanup";
import { allInspectionsForRetention, listInvestigations } from "../storage";
import { syncOutbox, type SyncSummary } from "../sync";
import { styles } from "../theme";
import { EmptyState, ErrorState, ListSkeleton, OfflineBanner } from "../ui/states";
import { Header, Primary } from "../ui/primitives";
import type { FolderRow } from "../types";

const SORTS = [{key: "recent", label: "Recent"}, {key: "name", label: "Name"}] as const;

export function InvestigationsScreen() {
  const navigation = useNavigation();
  const {client, scope} = useSession();
  const [rows, setRows] = useState<FolderRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"recent" | "name">("recent");
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [blocked, setBlocked] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await listInvestigations(scope, {q: query, sort}));
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not read local storage");
    }
  }, [scope, query, sort]);

  const sync = useCallback(async () => {
    try {
      const summary: SyncSummary = await syncOutbox(client, scope);
      setOffline(summary.stoppedForConnection);
      setBlocked(summary.blocked);
    } catch (cause) {
      setOffline(isConnectionError(cause));
    }
    await load();
  }, [client, scope, load]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  useEffect(() => {
    // queueMicrotask, not a bare call: the effect body must not set state synchronously
    // or every sync schedules a cascading render.
    queueMicrotask(() => { void sync(); });
    // Once per launch: drop orphaned photographs (every retake used to leak one) and age
    // out downloaded reports. Never deletes evidence the server has not confirmed.
    queueMicrotask(() => {
      void allInspectionsForRetention(scope)
        .then((rows) => sweep(rows))
        .catch(() => undefined);
    });
    const network = NetInfo.addEventListener((state) => {
      if (state.isConnected && state.isInternetReachable !== false) void sync();
    });
    const app = AppState.addEventListener("change", (state) => {
      if (state === "active") void sync();
    });
    return () => { network(); app.remove(); };
  }, [sync, scope]);

  async function refresh() {
    setRefreshing(true);
    await sync();
    setRefreshing(false);
  }

  return <View style={styles.flex}>
    <Header title="Investigations" action="Account"
            onAction={() => navigation.navigate("Settings")} />
    <OfflineBanner visible={offline} blocked={blocked} />
    <View style={{padding: 16, paddingBottom: 8, gap: 10}}>
      <TextInput style={styles.searchBox} value={query} onChangeText={setQuery}
                 placeholder="Search name, brand or place" placeholderTextColor="#93a29a"
                 autoCorrect={false} returnKeyType="search" />
      <View style={{flexDirection: "row", gap: 8}}>
        {SORTS.map((option) =>
          <Pressable key={option.key} onPress={() => setSort(option.key)}
                     style={[styles.statChip, sort === option.key && {backgroundColor: "#1e6647"}]}>
            <Text style={[styles.statChipText, sort === option.key && {color: "#fff"}]}>
              {option.label}</Text>
          </Pressable>)}
      </View>
    </View>

    {rows === null
      ? <View style={{padding: 16}}><ListSkeleton /></View>
      : error
        ? <View style={{padding: 16}}><ErrorState message={error} retry={load} /></View>
        : <FlatList
            data={rows}
            keyExtractor={(row) => row.client_uuid}
            contentContainerStyle={{padding: 16, paddingTop: 4, gap: 10, paddingBottom: 90}}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
            initialNumToRender={12}
            windowSize={7}
            removeClippedSubviews
            ListEmptyComponent={
              <EmptyState
                title={query ? "Nothing matches that" : "No investigations yet"}
                body={query
                  ? "Try a different name, brand or place."
                  : "An investigation is a folder — a market sweep, a manufacturer audit, a complaint. Create one, then scan products into it."}
                action={query ? undefined : "New investigation"}
                onAction={query ? undefined : () => navigation.navigate("InvestigationEdit", {})} />}
            renderItem={({item}) => <FolderCard row={item}
              onPress={() => navigation.navigate("Investigation",
                                                 {investigationId: item.client_uuid})} />} />}

    <View style={{position: "absolute", left: 16, right: 16, bottom: 18}}>
      <Primary label="New investigation"
               onPress={() => navigation.navigate("InvestigationEdit", {})} />
    </View>
  </View>;
}

function FolderCard({row, onPress}: {row: FolderRow; onPress: () => void}) {
  const place = [row.subject_brand, row.location_text].filter(Boolean).join(" · ");
  return <Pressable onPress={onPress} style={styles.folderCard}>
    <Text style={styles.folderName}>{row.name}</Text>
    {!!place && <Text style={styles.folderMeta}>{place}</Text>}
    <View style={styles.folderStats}>
      <Text style={styles.folderStat}>{row.scan_count} scan{row.scan_count === 1 ? "" : "s"}</Text>
      {row.failed_count > 0 &&
        <Text style={[styles.folderStat, styles.folderStatBad]}>{row.failed_count} failing</Text>}
      {row.pending_count > 0 &&
        <Text style={styles.folderStat}>{row.pending_count} waiting to upload</Text>}
      {row.status === "CLOSED" && <Text style={styles.folderStat}>Closed</Text>}
      {!row.server_id && <Text style={styles.folderStat}>Not yet uploaded</Text>}
    </View>
  </Pressable>;
}
