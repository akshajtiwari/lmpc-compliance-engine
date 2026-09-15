/* One stack, session-gated at the root.
 *
 * No `linking` config is registered, deliberately. Our deep link — lmpc://enroll?…&token=
 * — carries a one-time enrollment token, and turning arbitrary lmpc:// URLs into
 * navigable routes would let any link drop an authenticated user onto any screen. The
 * enrollment URL stays handled imperatively inside the enrol screen. */
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { CaptureScreen } from "../screens/CaptureScreen";
import { InvestigationEditScreen } from "../screens/InvestigationEditScreen";
import { InvestigationScreen } from "../screens/InvestigationScreen";
import { InvestigationsScreen } from "../screens/InvestigationsScreen";
import { ListingCaptureScreen } from "../screens/ListingCaptureScreen";
import { ScanReportScreen } from "../screens/ScanReportScreen";
import { SettingsScreen } from "../screens/SettingsScreen";
import type { RootParamList } from "./routes";

const Stack = createNativeStackNavigator<RootParamList>();

export function RootNavigator() {
  return <NavigationContainer>
    <Stack.Navigator screenOptions={{headerShown: false}}>
      <Stack.Screen name="Investigations" component={InvestigationsScreen} />
      <Stack.Screen name="Investigation" component={InvestigationScreen} />
      <Stack.Screen name="InvestigationEdit" component={InvestigationEditScreen}
                    options={{presentation: "modal"}} />
      {/* A swipe back must not silently discard queued panels. */}
      <Stack.Screen name="Capture" component={CaptureScreen}
                    options={{presentation: "fullScreenModal", gestureEnabled: false}} />
      <Stack.Screen name="ListingCapture" component={ListingCaptureScreen}
                    options={{presentation: "fullScreenModal", gestureEnabled: false}} />
      <Stack.Screen name="ScanReport" component={ScanReportScreen} />
      <Stack.Screen name="Settings" component={SettingsScreen}
                    options={{presentation: "modal"}} />
    </Stack.Navigator>
  </NavigationContainer>;
}
