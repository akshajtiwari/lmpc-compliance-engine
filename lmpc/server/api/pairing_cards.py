"""The cards on the pairing page that decide and report reachability.

Split out of `pairing_page.py` to keep both inside the 200-line budget that
`tests/test_import_graph.py` enforces for everything under `server/api/`.
"""
from __future__ import annotations

from html import escape

KIND_LABELS = {
    "lan": "Local network",
    "public": "Public address",
    "tunnel": "VPN / tunnel",
    "virtual": "Container network",
    "inactive": "No link",
}


def address_card(state: dict, csrf: str) -> str:
    """Choose the address the QR carries.

    Automatic detection is right on a plain laptop and wrong on any machine carrying a
    VPN, so the choice is shown rather than hidden: the officer can see which address was
    picked, what else was found, and why the rest were passed over.
    """
    advertised = state["advertised_url"]
    port = state["port"]
    rows = "".join(_option(item, advertised, port) for item in state["candidates"])
    heading = (escape(advertised) if advertised
               else "No address found — type one below")
    return f"""<section class="card address-card" aria-labelledby="address-heading">
    <h2 id="address-heading">Where the phone will connect</h2>
    <p class="address-now mono break">{heading}</p>
    <p class="muted">This is the address inside the QR code. The phone must be able to
    reach it — if it cannot, the app reports that it could not reach the server.</p>
    <form method="post" action="/pair/address">
      <input type="hidden" name="csrf" value="{escape(csrf)}">
      <ul class="addresses">{rows or _nothing_found()}</ul>
      <p class="field">
        <label for="custom">Or a different address — a remote server, a public host
        name, or a tunnel:</label>
        <input type="text" id="custom" name="custom" class="mono"
               placeholder="https://lmpc.example.gov.in"
               autocomplete="off" spellcheck="false">
      </p>
      <button type="submit" class="primary">Use this address</button>
      {_reset_button(state)}
    </form>
    {_address_error(state)}
  </section>"""


def _option(candidate, advertised: str | None, port: int) -> str:
    url = candidate.url(port)
    checked = " checked" if advertised == url else ""
    disabled = "" if candidate.usable else " disabled"
    classes = "address" + ("" if candidate.usable else " unusable")
    where = f" · {escape(candidate.interface)}" if candidate.interface else ""
    routed = '<span class="tag">default route</span>' if candidate.routed else ""
    return f"""<li class="{classes}">
      <label>
        <input type="radio" name="choice" value="{escape(candidate.host)}"{checked}{disabled}>
        <span class="mono">{escape(url)}</span>
        <span class="muted kind">{KIND_LABELS[candidate.kind]}{where}</span> {routed}
        <span class="muted why">{escape(candidate.note)}</span>
      </label>
    </li>"""


def _nothing_found() -> str:
    return ('<li class="address unusable"><span class="muted why">This computer reports '
            'no network address at all. Join a Wi-Fi network, or type the address the '
            'phone should use below.</span></li>')


def _reset_button(state: dict) -> str:
    if not state["overridden"]:
        return ""
    return ('<button type="submit" name="reset" value="on" class="secondary">'
            'Back to automatic</button>')


def _address_error(state: dict) -> str:
    message = state.get("address_error")
    if not message:
        return ""
    return f'<p class="error" role="alert">{escape(message)}</p>'


def network_card(state: dict, csrf: str) -> str:
    """The LAN switch, plus what has actually reached this machine."""
    on = state["network_open"]
    advertised = state["advertised_url"]
    summary = (f"Phones can reach the server at {escape(advertised)}."
               if on and advertised else
               "Phones can reach the server." if on else
               "Nothing outside this computer is being answered yet. "
               "Turn this on to let the phone connect.")
    return f"""<section class="card switch-card">
    <div>
      <h2>Phone connections {'allowed' if on else 'blocked'}</h2>
      <p class="muted">{summary}</p>
      {contact_line(state)}
    </div>
    <form method="post" action="/pair/network">
      <input type="hidden" name="csrf" value="{escape(csrf)}">
      <input type="hidden" name="allow" value="{'' if on else 'on'}">
      <button type="submit" class="{'danger' if on else 'primary'}">
        {'Block' if on else 'Allow phone connections'}</button>
    </form>
  </section>"""


def contact_line(state: dict) -> str:
    """What reached this machine last, and whether it was let through.

    Without this the officer is debugging blind: a phone that is dialling the right
    address and being refused looks exactly like a phone that cannot find the machine.
    """
    contact = state.get("last_contact")
    if not contact:
        return ('<p class="contact muted" id="contact">Nothing on the network has '
                'reached this computer yet.</p>')
    when = _ago(contact["seconds_ago"])
    if contact["allowed"]:
        return (f'<p class="contact good" id="contact">A device at '
                f'{escape(contact["peer"])} reached this computer {when}.</p>')
    return (f'<p class="contact warn-text" id="contact">A device at '
            f'{escape(contact["peer"])} reached this computer {when} and was refused — '
            f'allow phone connections above.</p>')


def _ago(seconds: int) -> str:
    if seconds < 5:
        return "just now"
    if seconds < 90:
        return f"{seconds} seconds ago"
    return f"{seconds // 60} minutes ago"
