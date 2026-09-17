LMPC Compliance — Windows portable preview
===========================================

1. Extract the whole ZIP. Do not run the EXE from inside the ZIP viewer.
2. Double-click LMPC-Compliance.exe.
3. Keep the server window open while using the app in your browser.
4. Press Ctrl+C in the server window to stop the app.

Connecting a phone
------------------
The app opens a "Connect a phone" page in your browser. Put the phone on the same Wi-Fi,
click "Allow phone connections", then scan the QR code with LMPC Field. If the camera
will not scan, the page also prints a server address, email and password you can type
into the app instead. The same QR is drawn in the server window.

If the phone says it cannot reach the server
--------------------------------------------
The QR carries one address, and the phone has to be able to reach that exact address. The
page lists every address this computer has, marks the ones a phone could dial, and says
why the others cannot be reached -- a VPN endpoint or a Docker network is private to this
computer, and a VPN is usually the address an automatic guess would pick.

  * Choose a different address on the page if the phone is on another network, then scan
    the new code. Changing the address issues a new one.
  * Type an address instead, if the server is reached some other way -- a public host
    name, a port-forward, or a tunnel.
  * The switch card reports the last device that reached this computer and whether it was
    allowed through. A device shown as refused has found the right address already.

Windows will ask once, at startup, whether to allow LMPC Compliance through the firewall.
Allow it on private networks only. The app answers nothing from the network until you
click "Allow phone connections", and the pairing page itself is only ever served to this
computer — a phone that requests it is refused.

Where things are kept
---------------------
Immutable image and report files live under %LOCALAPPDATA%\LMPC Compliance\objects.
Scans, investigations and reports persist in a SQLite database beside them and survive a
restart. The PostgreSQL stack documented in README.md is the multi-user configuration.

This preview carries traffic as unencrypted HTTP over your local network. Use it on a
private network you control. A deployment holding real enforcement evidence needs HTTPS.

Diagnostics:
  LMPC-Compliance.exe --self-test
  LMPC-Compliance.exe --addresses            (list addresses a phone could dial)
  LMPC-Compliance.exe --no-browser --port 8765
  LMPC-Compliance.exe --loopback-only        (refuse phone connections entirely)

For a server nobody is sitting at:
  LMPC-Compliance.exe --allow-phones         (accept phones without a click)
  LMPC-Compliance.exe --public-url https://lmpc.example.gov.in
                                             (the address phones should dial)

Production legal use requires qualified Legal Metrology officer sign-off.
