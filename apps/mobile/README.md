# LMPC Field

Native Expo/React Native capture application for Android and iOS. The app photographs package surfaces, preserves queued evidence in SQLite and app-private storage, uploads over the local network, and shows an explanation button for every rule finding.

## Local device connection

1. Start the API from the repository root with `make dev-lan`.
2. Start Workbench from `apps/web` with `npm run dev -- --hostname 0.0.0.0`.
3. In Workbench, create a field-officer account and show its one-time enrollment QR.
4. Install/open LMPC Field on a phone connected to the same network and scan the QR.

Manual server/password sign-in is available as a development fallback. The preview native configuration permits plain HTTP only to support the current local-server requirement; production deployment must use HTTPS and remove broad clear-text allowances.

## Development checks

```bash
npm install
npm run typecheck
npm run doctor
npx expo export --platform android
```

## Standalone Android preview

An `assembleDebug` APK expects Metro and is not distributable as a standalone app. The
preview workflow deliberately builds the release variant (still signed with the
development key) and verifies that `assets/index.android.bundle` exists inside the APK.

To reproduce that build with an Android SDK installed:

```bash
LMPC_FIELD_PREVIEW_HTTP=1 npx expo prebuild --platform android --no-install --clean
cd android
./gradlew assembleRelease --no-daemon
unzip -Z1 app/build/outputs/apk/release/app-release.apk > apk-entries.txt
grep -Fx assets/index.android.bundle apk-entries.txt
```
