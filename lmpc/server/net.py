"""Local network facts the server needs to advertise itself to a phone."""
from __future__ import annotations

import ipaddress
import socket

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def lan_address() -> str | None:
    """Return a routable private IPv4 address, without sending application data.

    Connecting a UDP socket to a TEST-NET-1 address transmits nothing; it only asks the
    routing table which local interface would be used to reach the outside world.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
    except OSError:
        try:
            address = socket.gethostbyname(socket.gethostname())
        except OSError:
            return None
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return None
    return address if (parsed.version == 4 and parsed.is_private
                       and not parsed.is_loopback) else None


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
