"""Which address a phone should be told to dial, and whether a request came from here.

The hard part is not finding *an* address. It is finding one the phone can actually
reach, on a machine that also holds a VPN tunnel, a handful of container bridges, and
whatever else the officer's IT department installed. `lan_candidates` ranks them and says
why; `lan_address` picks the winner for callers that only want one.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from .ifaces import Interface, enumerate_ipv4

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True)
class Candidate:
    """One address the pairing page may offer, with the reason for its rank."""

    host: str
    interface: str
    kind: str            # "lan" | "public" | "tunnel" | "virtual" | "inactive"
    note: str
    routed: bool         # the address the routing table would have chosen

    @property
    def usable(self) -> bool:
        """Whether a phone on the officer's network has any chance of reaching it."""
        return self.kind in ("lan", "public")

    def url(self, port: int) -> str:
        return f"http://{self.host}:{port}"


def routed_address() -> str | None:
    """The address the routing table would use to leave this machine.

    Connecting a UDP socket to a TEST-NET-1 address transmits nothing; it only asks the
    routing table which local interface would be used to reach the outside world. This is
    the right answer for outbound traffic and the wrong one for inbound pairing, so it is
    used only to mark a candidate, never to choose one.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
    except OSError:
        return None


def lan_candidates() -> list[Candidate]:
    """Every address this machine holds, best first, each labelled with why."""
    routed = routed_address()
    found = [_classify(item, routed) for item in enumerate_ipv4()]
    if not found and routed:
        # Enumeration found nothing at all: fall back to the one address we can always
        # get, rather than telling the officer there is no network.
        found = [_classify(Interface(name="", address=routed, prefix=None,
                                     point_to_point=False, running=True), routed)]
    return sorted(found, key=_rank)


def lan_address() -> str | None:
    """A private address a phone on the same network can reach, or None.

    Callers that want any reachable address, public ones included, should use
    `lan_candidates`. This stays private-only because `server/run.py --lan` uses it to
    decide whether it is safe to bind a wider socket.
    """
    for candidate in lan_candidates():
        if candidate.usable and _private(candidate.host):
            return candidate.host
    return None


def best_address() -> str | None:
    """The address to advertise when nothing better was configured by hand."""
    for candidate in lan_candidates():
        if candidate.usable:
            return candidate.host
    return None


def is_loopback(host: str | None) -> bool:
    """True when a request came from this machine.

    Used to keep the pairing page off the network: it hands out credentials, so only
    somebody sitting at the computer may see it.
    """
    if not host:
        return False
    if host in LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalise_base_url(value: str, *, default_port: int | None = None) -> str:
    """Accept only what `apps/mobile/src/api.ts::normalizeServerUrl` will accept.

    Validating here means the officer is told on the page, where they can fix it, rather
    than by a phone that has already scanned a QR it cannot use.
    """
    text = (value or "").strip().rstrip("/")
    if not text:
        raise ValueError("Enter a server address")
    bare = "://" not in text
    if bare:
        text = f"http://{text}"
    parsed = urlsplit(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("The address must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("The address is missing a host name")
    if parsed.username or parsed.password:
        raise ValueError("The address must not carry a user name or password")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("The address must not carry a path, query or fragment")
    try:
        port = parsed.port
    except ValueError as cause:
        raise ValueError("The port must be a number") from cause
    # A bare host is somebody typing an address off this page, so fill in the port they
    # can see in the URL bar. A typed-out http:// URL is left exactly as given.
    if port is None and default_port and bare:
        return f"{text}:{default_port}"
    return text


# ---- classification ------------------------------------------------------------------

def _classify(item: Interface, routed: str | None) -> Candidate:
    routed_here = item.address == routed
    if item.point_to_point or item.host_route:
        return Candidate(
            item.address, item.name, "tunnel", routed=routed_here,
            note="A VPN or tunnel endpoint. It belongs to this machine alone, so a "
                 "phone on the Wi-Fi cannot reach it.")
    if item.virtual:
        return Candidate(
            item.address, item.name, "virtual", routed=routed_here,
            note="A container or virtual-machine network on this computer. Nothing "
                 "outside this computer can reach it.")
    if not item.running:
        return Candidate(item.address, item.name, "inactive", routed=routed_here,
                         note="This interface has no link. Nothing is connected to it.")
    if _private(item.address):
        return Candidate(item.address, item.name, "lan", routed=routed_here,
                         note="A local network address. Use this when the phone is on "
                              "the same Wi-Fi as this computer.")
    return Candidate(item.address, item.name, "public", routed=routed_here,
                     note="A public address. A phone can reach it from anywhere, if the "
                          "network allows the port through.")


_ORDER = {"lan": 0, "public": 1, "tunnel": 2, "virtual": 3, "inactive": 4}


def _rank(candidate: Candidate) -> tuple[int, int, str]:
    # Within a class the routed address wins: on a plain laptop it is the right answer,
    # and on this machine it is the only one the officer will recognise.
    return (_ORDER[candidate.kind], 0 if candidate.routed else 1, candidate.host)


def _private(host: str) -> bool:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.is_private and not parsed.is_loopback
