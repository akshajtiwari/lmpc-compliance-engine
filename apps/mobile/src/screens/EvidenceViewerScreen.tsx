/* Every photograph taken for one inspection, with what was measured about it.
 *
 * The capture screen already computes sharpness, exposure and glare for each frame and
 * then discards the numbers after the Keep/Retake prompt. They belong in the evidence
 * trail: whether a photograph was good enough is part of why a finding stands. */
import { useEffect, useState } from "react";
import { Image, ScrollView, Text, View, useWindowDimensions } from "react-native";
import { useNavigation, useRoute, type RouteProp } from "@react-navigation/native";

import { useSession } from "../session";
import { findInspection } from "../storage";
import { styles } from "../theme";
import { EmptyState } from "../ui/states";
import { Header } from "../ui/primitives";
import type { CapturedPanel, Draft, ScanResult } from "../types";
import type { RootParamList } from "../navigation/routes";

export function EvidenceViewerScreen() {
  const navigation = useNavigation();
  const route = useRoute<RouteProp<RootParamList, "EvidenceViewer">>();
  const {scope} = useSession();
  const {width} = useWindowDimensions();
  const [panels, setPanels] = useState<CapturedPanel[] | null>(null);
  const [hashes, setHashes] = useState<Record<string, string>>({});
  const [coverage, setCoverage] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    queueMicrotask(() => {
      void findInspection(route.params.clientUuid, scope).then((row) => {
        if (!alive || !row) { if (alive) setPanels([]); return; }
        try {
          const draft = JSON.parse(row.draft_json) as Draft;
          setPanels(draft.panels ?? []);
          setCoverage(draft.coverageAsserted ?? null);
        } catch { setPanels([]); }
        if (!row.result_json) return;
        try {
          const result = JSON.parse(row.result_json) as ScanResult;
          setHashes(Object.fromEntries(
            (result.images ?? []).map((image) => [image.panel, image.sha256])));
        } catch { /* the trail still renders without server hashes */ }
      });
    });
    return () => { alive = false; };
  }, [route.params.clientUuid, scope]);

  return <View style={styles.flex}>
    <Header title="Evidence" action="Back" onAction={navigation.goBack} />
    <ScrollView contentContainerStyle={styles.page}>
      {coverage === false && <View style={styles.warning}>
        <Text style={styles.warningTitle}>Coverage not asserted</Text>
        <Text style={styles.warningText}>
          Not every panel was taken through the guided camera, so this inspection cannot
          state that a declaration is absent — only that it was not found.
        </Text>
      </View>}
      {panels === null
        ? null
        : panels.length === 0
          ? <EmptyState title="No photographs on this phone"
                        body="The evidence for this inspection is held on the server." />
          : panels.map((panel) => <View key={panel.panel + panel.uri}
                                        style={[styles.folderCard, {marginBottom: 12}]}>
              <Text style={styles.folderName}>{panel.panel.replaceAll("_", " ")}</Text>
              {/* Pinch-zoom would need gesture-handler and reanimated; this fits the
                  frame to the screen on both platforms rather than pretending. */}
              <Image source={{uri: panel.uri}}
                     style={{width: width - 72, height: (width - 72) * 0.7,
                             borderRadius: 8, backgroundColor: "#eef2ed"}}
                     resizeMode="contain" />
              <Text style={styles.folderMeta}>
                {panel.source === "CAMERA" ? "Photographed in the app" : "Imported from gallery"}
              </Text>
              {panel.quality && <Text style={styles.noteMeta}>
                sharpness {panel.quality.sharpness?.toFixed?.(0) ?? "—"} ·
                brightness {panel.quality.mean_luma?.toFixed?.(0) ?? "—"} ·
                glare {((panel.quality.glare_fraction ?? 0) * 100).toFixed(1)}%
                {panel.quality.warnings?.length
                  ? ` · ${panel.quality.warnings.join(", ")}` : ""}
              </Text>}
              {hashes[panel.panel] && <Text style={styles.noteMeta}>
                SHA-256 held by the server: {hashes[panel.panel].slice(0, 24)}…
              </Text>}
            </View>)}
    </ScrollView>
  </View>;
}
