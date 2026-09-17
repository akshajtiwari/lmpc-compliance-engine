"""The HTML for the desktop pairing page.

Plain server-rendered markup with an external stylesheet and script, because the app's
Content-Security-Policy is `default-src 'self'` with no `unsafe-inline` — an inline
<style> or <script> here would be silently dropped by the browser.
"""
from __future__ import annotations

from html import escape

from .pairing_cards import address_card, network_card


def render(state: dict, csrf: str) -> str:
    advertised = state["advertised_url"]
    ready = bool(advertised)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect a phone — LMPC Compliance</title>
<link rel="stylesheet" href="/pair.css">
<link rel="icon" href="/icon.svg">
</head>
<body>
<main class="pair">
  <header>
    <h1>Connect a phone</h1>
    <p class="lede">Open <strong>LMPC Field</strong> on the phone and scan this code.
    The phone needs to be able to reach the address below — the same Wi-Fi is the usual
    way, but any network that can reach it will do.</p>
  </header>

  {address_card(state, csrf)}

  {network_card(state, csrf)}

  <section class="card qr-card" aria-labelledby="qr-heading">
    <h2 id="qr-heading">Scan to connect</h2>
    {_qr_block(state, ready)}
    <p class="status" id="status" data-open="{str(state['network_open']).lower()}">
      {_status_text(state, ready)}</p>
    <form method="post" action="/pair/enrollment" class="inline-form">
      <input type="hidden" name="csrf" value="{escape(csrf)}">
      <button type="submit" class="secondary">New code</button>
    </form>
  </section>

  <section class="card" aria-labelledby="manual-heading">
    <h2 id="manual-heading">If the camera will not scan</h2>
    <p>In the app, choose <em>Can’t scan? Use server sign-in</em> and type:</p>
    <dl class="kv">
      <dt>Server</dt><dd class="mono break">{escape(advertised or 'no address yet')}</dd>
      <dt>Email</dt><dd class="mono">{escape(state['officer_email'])}</dd>
      <dt>Password</dt><dd class="mono">{escape(state['officer_password'])}</dd>
    </dl>
  </section>

  <details class="card">
    <summary>Supervisor sign-in and server identity</summary>
    <dl class="kv">
      <dt>Email</dt><dd class="mono">{escape(state['supervisor_email'])}</dd>
      <dt>Password</dt><dd class="mono">{escape(state['supervisor_password'])}</dd>
      <dt>Fingerprint</dt><dd class="mono break">{escape(state['fingerprint'])}</dd>
    </dl>
    <p class="muted">The phone checks that fingerprint against the server it reaches. If
    the app reports a mismatch, stop — something else answered.</p>
  </details>

  <p class="warn"><strong>Preview build.</strong> Traffic on this network is unencrypted
  HTTP. Use it on a private Wi-Fi network you control. A deployment that carries real
  enforcement evidence needs HTTPS.</p>
</main>
<script src="/pair.js"></script>
</body>
</html>
"""


def _qr_block(state: dict, ready: bool) -> str:
    if not ready:
        return ('<p class="muted">Choose an address above and the code will appear.</p>')
    if not state["network_open"]:
        return ('<div class="qr-dim"><img src="/pair/qr.svg" alt="Enrollment QR code" '
                'width="260" height="260">'
                '<p class="overlay">Allow phone connections first</p></div>')
    return ('<img src="/pair/qr.svg" alt="Enrollment QR code" width="260" height="260">')


def _status_text(state: dict, ready: bool) -> str:
    if not ready:
        return "Waiting for an address."
    if not state["network_open"]:
        return "The code will work once connections are allowed."
    enrolled = state["devices_enrolled"]
    if enrolled:
        return f"{enrolled} phone{'s' if enrolled > 1 else ''} connected. Scan again to add another."
    return "Waiting for a phone… the code expires in 15 minutes."
