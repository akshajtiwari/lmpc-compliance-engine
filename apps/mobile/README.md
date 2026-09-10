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
