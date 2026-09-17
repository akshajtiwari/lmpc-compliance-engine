"""What the portable build tells the person who started it.

The browser may not open — a headless machine, a locked-down default browser, a remote
session — so the console has to carry the pairing code and, when pairing fails, the
reason. Kept out of `desktop.py` so that file stays inside its line budget.
"""
from __future__ import annotations


def print_pairing_banner(pairing, host: str) -> None:
    """The address, the QR, and what to do when neither is what was expected."""
    if host == "127.0.0.1":
        print("Loopback only: phones cannot reach this computer. "
              "Restart without --loopback-only to pair one.")
        return
    print_addresses()
    advertised = pairing.lan_url()
    if not advertised:
        print("\nNo usable network address found. Join the same Wi-Fi as the phone, or "
              "restart with --public-url to name the address the phone should dial.")
        return
    print(f"\nPhone address: {advertised}")
    print("Phone connections are already allowed. Scan:\n" if pairing.network_open else
          "Open the page above and click 'Allow phone connections', then scan:\n")
    try:
        print(pairing.qr_terminal())
    except Exception:                       # pragma: no cover - console encoding
        print("(This console cannot draw the code — use the page in the browser.)")


def print_addresses() -> int:
    """List every address this machine holds, and say which a phone could reach.

    A VPN or a container bridge takes the default route and hands out an address only
    this machine can reach. A phone dialling it reports that it cannot reach the server,
    which reads to an officer as the two being on different networks. Printing the whole
    list, with the reason each was ranked where it was, makes that visible.
    """
    from lmpc.server.net import lan_candidates

    candidates = lan_candidates()
    if not candidates:
        print("No network addresses found on this computer.")
        return 0
    print("\nAddresses on this computer:")
    for item in candidates:
        mark = "usable  " if item.usable else "no      "
        where = f" ({item.interface})" if item.interface else ""
        print(f"  {mark}{item.host}{where}")
        print(f"          {item.note}")
    return 0
