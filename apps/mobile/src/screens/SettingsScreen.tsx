/* Moved verbatim from App.tsx; only the imports are new. */
import { Alert, Pressable, ScrollView, Text, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useSession } from "../session";
import { Header, Logo } from "../ui/primitives";
import { styles } from "../theme";
import type { Session } from "../types";

function SettingsBody({session,close,logout}:{session:Session;close:()=>void;logout:()=>void}) {return <View style={styles.flex}><Header title="Account & server" action="Done" onAction={close}/><ScrollView contentContainerStyle={styles.page}><Logo/><Text style={styles.h1}>{session.user.full_name}</Text><Text style={styles.body}>{session.user.email} · {session.user.role.replaceAll("_"," ")}</Text><View style={styles.nextCard}><Text style={styles.nextLabel}>LOCAL SERVER</Text><Text style={styles.mono}>{session.serverUrl}</Text><Text style={styles.nextLabel}>SERVER FINGERPRINT</Text><Text style={styles.fingerprint}>{session.fingerprint}</Text></View><View style={styles.warning}><Text style={styles.warningTitle}>Local preview security</Text><Text style={styles.warningText}>This preview permits HTTP on the local network. Use HTTPS and managed device policy before a production rollout.</Text></View><Pressable style={styles.dangerButton} onPress={()=>Alert.alert("Remove this device?","A new Workbench enrollment QR will be required.",[{text:"Cancel",style:"cancel"},{text:"Remove",style:"destructive",onPress:logout}])}><Text style={styles.dangerText}>Remove account from this device</Text></Pressable></ScrollView></View>;}


export function SettingsScreen() {
  const navigation = useNavigation();
  const {session, client, setSession} = useSession();
  return <SettingsBody session={session} close={() => navigation.goBack()}
    logout={async () => { await client.logout(); setSession(null); }} />;
}
