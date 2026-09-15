/* Open a new investigation.
 *
 * Written locally first and synced through the outbox, so a folder can be started in a
 * market with no signal and still be the same folder when the phone reconnects — the
 * client UUID is what makes the server's create idempotent. */
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { randomUUID } from "expo-crypto";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";

import { useSession } from "../session";
import { createInvestigation } from "../storage";
import { syncOutbox } from "../sync";
import { styles } from "../theme";
import { Choice, Field, Header, Primary } from "../ui/primitives";
import type { RootParamList } from "../navigation/routes";

const TYPES = ["RETAIL_SWEEP", "MANUFACTURER_AUDIT", "ECOMMERCE_SWEEP", "COMPLAINT",
               "MARKET_SURVEY", "OTHER"];

export function InvestigationEditScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootParamList>>();
  const {client, scope} = useSession();
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [place, setPlace] = useState("");
  const [kind, setKind] = useState("RETAIL_SWEEP");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (!name.trim()) { setError("Give this investigation a name."); return; }
    setBusy(true); setError("");
    const clientUuid = randomUUID();
    try {
      await createInvestigation({
        clientUuid, name: name.trim(), subjectBrand: brand.trim() || undefined,
        investigationType: kind, locationText: place.trim() || undefined,
      }, scope);
      // Best effort: the folder is already on the phone, so a failure here is not an
      // error the officer needs to see — the outbox will carry it.
      void syncOutbox(client, scope).catch(() => undefined);
      navigation.replace("Investigation", {investigationId: clientUuid});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this investigation");
      setBusy(false);
    }
  }

  return <View style={styles.flex}>
    <Header title="New investigation" action="Cancel" onAction={navigation.goBack} />
    <KeyboardAvoidingView style={styles.flex}
                          behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.page}>
        <Text style={styles.eyebrow}>THE FOLDER</Text>
        <Text style={styles.h1}>What are you inspecting?</Text>
        <Field label="NAME" value={name} onChangeText={setName}
               placeholder="Britannia sweep" autoFocus />
        <Field label="BRAND OR MANUFACTURER (OPTIONAL)" value={brand}
               onChangeText={setBrand} placeholder="Britannia" />
        <Field label="PLACE (OPTIONAL)" value={place} onChangeText={setPlace}
               placeholder="Sector 14 market" />
        <Text style={styles.label}>TYPE</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.choiceScroll}>
          {TYPES.map((value) =>
            <Choice key={value} value={value.replaceAll("_", " ")}
                    selected={kind === value} onPress={() => setKind(value)} />)}
        </ScrollView>
        {!!error && <Text style={styles.error}>{error}</Text>}
        <Primary label={busy ? "Saving…" : "Create and open"} onPress={save} disabled={busy} />
        <Text style={styles.stateBody}>
          This is saved on the phone straight away. If there is no connection it uploads
          when there is one.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  </View>;
}
