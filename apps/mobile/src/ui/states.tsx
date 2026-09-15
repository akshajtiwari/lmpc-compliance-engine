/* Empty, loading, error and offline states.
 *
 * The app had none of these: every failure was an Alert, and a refresh blanked the
 * screen. An officer standing in a shop needs to know whether a folder is empty, still
 * loading, or unreachable — those are three different situations with three different
 * next actions. */
import { ActivityIndicator, Pressable, Text, View } from "react-native";

import { styles } from "../theme";

export function EmptyState({title, body, action, onAction}: {
  title: string; body: string; action?: string; onAction?: () => void;
}) {
  return <View style={styles.stateBox}>
    <Text style={styles.stateTitle}>{title}</Text>
    <Text style={styles.stateBody}>{body}</Text>
    {action && onAction && <Pressable onPress={onAction} style={styles.stateAction}>
      <Text style={styles.stateActionText}>{action}</Text></Pressable>}
  </View>;
}

export function ErrorState({message, retry}: {message: string; retry?: () => void}) {
  return <View style={[styles.stateBox, styles.stateError]}>
    <Text style={styles.stateTitle}>That did not load</Text>
    <Text style={styles.stateBody}>{message}</Text>
    {retry && <Pressable onPress={retry} style={styles.stateAction}>
      <Text style={styles.stateActionText}>Try again</Text></Pressable>}
  </View>;
}

export function ListSkeleton({rows = 3}: {rows?: number}) {
  return <View style={{gap: 10}}>
    {Array.from({length: rows}, (_, index) =>
      <View key={index} style={styles.skeletonRow} />)}
  </View>;
}

export function OfflineBanner({visible, blocked = 0}: {visible: boolean; blocked?: number}) {
  if (!visible && !blocked) return null;
  return <View style={styles.offlineBanner}>
    <Text style={styles.offlineText}>
      {visible
        ? "No connection to the server. Scans are saved on this phone and will upload."
        : `${blocked} scan${blocked === 1 ? "" : "s"} waiting for their investigation to upload first.`}
    </Text>
  </View>;
}

export function InlineSpinner({label}: {label: string}) {
  return <View style={styles.inlineSpinner}>
    <ActivityIndicator color="#1e6647" />
    <Text style={styles.stateBody}>{label}</Text>
  </View>;
}
