Installable LMPC Field Android preview for local-network testing.

**The app is now the officer's control surface.** Create an investigation, work inside it,
and never open the laptop again:

- **Pair from the desktop app itself.** Run `LMPC-Compliance.exe`, click *Allow phone
  connections*, and scan the QR it shows. The Workbench stack is no longer required — the
  previous preview could not issue an enrollment QR at all.
- **Investigations are folders.** Give one a name, a brand, a place and a type, then scan
  product after product into it. Search, sort and reopen them at any time.
- **Every report stays readable.** Results are cached on the phone, so a past inspection
  opens with no signal. Download any finalised report as PDF or DOCX.
- Capture front, back and optional side-panel evidence; blurry, dark, bright or
  glare-washed frames are flagged before upload with a retake prompt.
- Queue evidence offline and retry on the department LAN — each panel image is uploaded
  separately and idempotently, so an interrupted sync resumes instead of restarting. A
  folder created offline syncs before the scans that name it.
- Per-inspection notes, an evidence viewer showing how each photograph was taken and the
  hash the server holds, and a plain-language explanation for every rule result.

This is a standalone release-mode preview APK, signed with the development key, that
permits local HTTP. It includes the JavaScript bundle and does not require Metro or a USB
connection. It is not a production-store build.

**Not yet validated on physical hardware.** This build passes typecheck, lint, unit tests,
expo-doctor and a bundle export, and the APK is verified to contain its JavaScript bundle
before publication — but no device drill has been run against it. Treat it as a preview to
test, not as a build to rely on. In particular the local database schema changed in this
release: installing over an older build has not been exercised.
