LMPC Compliance — Windows portable preview
===========================================

1. Extract the whole ZIP. Do not run the EXE from inside the ZIP viewer.
2. Double-click LMPC-Compliance.exe.
3. Keep the server window open while using the app in your browser.
4. Press Ctrl+C in the server window to stop the app.

The server listens only on http://127.0.0.1:8000 and does not use S3. Immutable image
and report files are stored under %LOCALAPPDATA%\LMPC Compliance\objects. Scan records
in this portable preview live for the current server session; the PostgreSQL local stack
documented in README.md is the durable, multi-user configuration.

Diagnostics:
  LMPC-Compliance.exe --self-test
  LMPC-Compliance.exe --no-browser --port 8765

Production legal use requires qualified Legal Metrology officer sign-off.
