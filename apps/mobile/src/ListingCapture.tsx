// E-commerce listing capture (plan §6.4). A third-party listing is judged by
// Rule 6(10): what the shopper can see. The officer pastes the shopper-visible
// text, optionally the source URL, and attaches up to six screenshots. Screenshots
// never assert physical-package coverage — the server enforces that boundary.
import * as ImagePicker from "expo-image-picker";
import { randomUUID } from "expo-crypto";
import { useCallback, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from "react-native";
import { ApiClient } from "./api";
import { listingPanels } from "./quad";
import { queueDraft } from "./storage";
import { syncDraft } from "./sync";
import type { AccountScope, CapturedPanel, Draft, ScanResult } from "./types";

const CATEGORIES = ["FOOD", "COSMETIC", "GENERIC", "CEMENT", "FERTILIZER",
  "FARM_PRODUCE", "TOBACCO", "DRUG_FORMULATION", "MEDICAL_DEVICE"];
const MAX_SCREENSHOTS = 6;

export function ListingCapture({scope, client, cancel, complete}: {
  scope: AccountScope;
  client: ApiClient;
  cancel: () => void;
  complete: (result: ScanResult) => void;
}) {
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState("GENERIC");
  const [screenshots, setScreenshots] = useState<CapturedPanel[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const addScreenshot = useCallback(async () => {
    if (screenshots.length >= MAX_SCREENSHOTS) return;
    const result = await ImagePicker.launchImageLibraryAsync(
      {mediaTypes: ["images"], quality: 0.9});
    if (result.canceled) return;
    const asset = result.assets[0];
    const panel = listingPanels(screenshots.length + 1).at(-1)!;
    setScreenshots((previous) => [...previous, {panel, uri: asset.uri,
      source: "GALLERY"}]);
  }, [screenshots.length]);

  async function submit() {
    if (!text.trim()) { setError("Paste the shopper-visible listing text first."); return; }
    if (!screenshots.length) { setError("Attach at least one screenshot of the listing."); return; }
    const draft: Draft = {
      clientUuid: randomUUID(),
      capturedAt: new Date().toISOString().slice(0, 10),
      category, buyerType: "RETAIL", packageShape: "RECTANGULAR",
      coverageAsserted: false,
      panels: screenshots,
      mode: "ECOMMERCE_LISTING",
      listing: {text, url: url.trim() || null},
    };
    setUploading(true); setError("");
    try {
      await queueDraft(draft, scope);
      complete(await syncDraft(client, scope, draft));
    } catch (cause) {
      if (cause instanceof Error && cause.message.includes("no longer available")) {
        setError(cause.message);
      } else {
        Alert.alert("Saved for retry", "The listing evidence is safe on this phone. "
          + "It will sync automatically when the local server is reachable.");
        cancel();
      }
    } finally {
      setUploading(false);
    }
  }

  if (uploading) {
    return <View style={styles.center}>
      <ActivityIndicator size="large" color="#1e6647" />
      <Text style={styles.hint}>Securing listing evidence and running the checks…</Text>
    </View>;
  }

  return (
    <View style={styles.flex}>
      <View style={styles.header}>
        <Text style={styles.title}>New listing inspection</Text>
        <Pressable onPress={cancel}><Text style={styles.link}>Cancel</Text></Pressable>
      </View>
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Text style={styles.hint}>
          Paste exactly what a shopper sees online. The engine checks the online
          display against Rule 6(10); screenshots are evidence, not package photographs.
        </Text>
        <Text style={styles.label}>SHOPPER-VISIBLE LISTING TEXT</Text>
        <TextInput style={[styles.input, styles.multiline]} multiline
          placeholder="Paste the listing description as shown to the shopper"
          placeholderTextColor="#839087" value={text} onChangeText={setText}
          maxLength={20000} />
        <Text style={styles.label}>SOURCE URL (OPTIONAL)</Text>
        <TextInput style={styles.input} autoCapitalize="none" keyboardType="url"
          placeholder="https://…" placeholderTextColor="#839087" value={url}
          onChangeText={setUrl} maxLength={2048} />
        <Text style={styles.label}>COMMODITY CATEGORY</Text>
        <View style={styles.choiceRow}>{CATEGORIES.map(value => (
          <Pressable key={value} style={[styles.choice,
            category === value && styles.choiceOn]} onPress={() => setCategory(value)}>
            <Text style={[styles.choiceText, category === value && styles.choiceTextOn]}>
              {value.replaceAll("_", " ")}
            </Text>
          </Pressable>))}
        </View>
        <Text style={styles.label}>SCREENSHOTS ({screenshots.length}/{MAX_SCREENSHOTS})</Text>
        <View style={styles.grid}>
          {screenshots.map((shot) => (
            <Pressable key={shot.panel} style={styles.shot}
              onPress={() => setScreenshots((previous) =>
                previous.filter(item => item.panel !== shot.panel))}>
              <Image source={{uri: shot.uri}} style={styles.thumbnail} />
              <Text style={styles.shotLabel}>{shot.panel.replaceAll("_", " ")} · tap to remove</Text>
            </Pressable>))}
          {screenshots.length < MAX_SCREENSHOTS && (
            <Pressable style={styles.add} onPress={addScreenshot}>
              <Text style={styles.plus}>＋</Text>
            </Pressable>)}
        </View>
        {!!error && <Text style={styles.error}>{error}</Text>}
        <Pressable style={[styles.primary, (!text.trim() || !screenshots.length)
            && styles.disabled]}
          disabled={!text.trim() || !screenshots.length} onPress={submit}>
          <Text style={styles.primaryText}>Submit and analyse</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1, backgroundColor: "#fafbf7"},
  center: {flex: 1, alignItems: "center", justifyContent: "center", gap: 14,
    padding: 30},
  page: {padding: 20, paddingBottom: 54},
  header: {flexDirection: "row", alignItems: "center", paddingHorizontal: 18,
    paddingTop: 12, justifyContent: "space-between"},
  title: {fontSize: 20, fontWeight: "800", color: "#17231d", flex: 1},
  link: {color: "#1e6647", fontWeight: "700", fontSize: 14},
  hint: {fontSize: 13, lineHeight: 19, color: "#627068", marginBottom: 14},
  label: {fontSize: 11, fontWeight: "700", letterSpacing: .8, color: "#637169",
    marginTop: 14, marginBottom: 8, textTransform: "uppercase"},
  input: {borderWidth: 1, borderColor: "#cbd5cd", backgroundColor: "white",
    color: "#17231d", borderRadius: 10, paddingHorizontal: 13, paddingVertical: 12,
    fontSize: 15},
  multiline: {minHeight: 130, textAlignVertical: "top"},
  choiceRow: {flexDirection: "row", flexWrap: "wrap", gap: 8},
  choice: {borderWidth: 1, borderColor: "#cad5cc", borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 9, backgroundColor: "white"},
  choiceOn: {backgroundColor: "#153e2d", borderColor: "#153e2d"},
  choiceText: {color: "#536159", fontSize: 11, fontWeight: "700"},
  choiceTextOn: {color: "white"},
  grid: {flexDirection: "row", flexWrap: "wrap", gap: 10},
  shot: {width: "31%", backgroundColor: "white", borderWidth: 1,
    borderColor: "#d6ddd7", borderRadius: 10, overflow: "hidden"},
  thumbnail: {width: "100%", height: 110, resizeMode: "cover"},
  shotLabel: {fontSize: 9, fontWeight: "700", color: "#637068", margin: 7},
  add: {width: "31%", height: 110, borderRadius: 10, borderWidth: 1,
    borderStyle: "dashed", borderColor: "#a9bcae", alignItems: "center",
    justifyContent: "center", backgroundColor: "white"},
  plus: {fontSize: 28, color: "#59806a"},
  error: {color: "#a72e2e", backgroundColor: "#fff0ef", borderRadius: 8,
    padding: 11, fontSize: 13, marginTop: 14},
  primary: {minHeight: 50, borderRadius: 11, backgroundColor: "#1e6647",
    alignItems: "center", justifyContent: "center", paddingHorizontal: 18,
    marginTop: 18},
  primaryText: {color: "white", fontSize: 15, fontWeight: "800"},
  disabled: {opacity: .45},
});