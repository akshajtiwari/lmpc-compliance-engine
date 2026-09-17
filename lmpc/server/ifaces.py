"""Every IPv4 address this machine actually holds — not just the one the router prefers.

The routing table answers a different question from the one pairing asks. It answers
"which interface reaches the internet", which on a machine running a VPN is the VPN: a
point-to-point /32 that no phone on the Wi-Fi can ever dial. Pairing needs the opposite
question — "which addresses can a phone on this network reach me at" — and that is a
property of the interfaces, so we enumerate them.

POSIX gets the real answer from getifaddrs(3) through ctypes, which carries the netmask
and the interface flags; those flags are what tells a tunnel apart from a Wi-Fi card.
Windows has no getifaddrs, so it falls back to resolving the host name, which the
platform answers with every adapter address. That fallback loses the flags, which is why
the pairing page lets a human pick when more than one address is on offer.
"""
from __future__ import annotations

import ctypes
import ipaddress
import socket
import struct
import sys
from dataclasses import dataclass

IFF_UP = 0x1
IFF_LOOPBACK = 0x8
IFF_POINTOPOINT = 0x10
IFF_RUNNING = 0x40

# Interfaces that exist to serve containers and virtual machines. They are up, they carry
# a private address, and nothing on the officer's Wi-Fi can reach any of them.
VIRTUAL_PREFIXES = ("docker", "br-", "virbr", "vmnet", "vboxnet", "veth", "cni", "flannel",
                    "tailscale", "zt", "wg", "tun", "tap", "utun", "ppp")


@dataclass(frozen=True)
class Interface:
    """One IPv4 address, with enough context to judge whether a phone could reach it."""

    name: str
    address: str
    prefix: int | None
    point_to_point: bool
    running: bool

    @property
    def virtual(self) -> bool:
        return self.name.lower().startswith(VIRTUAL_PREFIXES)

    @property
    def host_route(self) -> bool:
        """A /32 belongs to exactly one machine, so it is a tunnel endpoint, not a LAN."""
        return self.prefix == 32


def enumerate_ipv4() -> list[Interface]:
    """Every non-loopback IPv4 address this machine has, best effort, never raising."""
    try:
        found = _windows_addresses() if sys.platform == "win32" else _posix_addresses()
    except Exception:              # pragma: no cover - platform/libc variation
        found = []
    seen: dict[str, Interface] = {}
    for item in found:
        if item.address not in seen:
            seen[item.address] = item
    return list(seen.values())


# ---- POSIX: getifaddrs(3) ------------------------------------------------------------

class _Sockaddr(ctypes.Structure):
    # Only the leading 16 bytes are read, which is all a sockaddr_in occupies.
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


class _Ifaddrs(ctypes.Structure):
    pass


_Ifaddrs._fields_ = [
    ("ifa_next", ctypes.POINTER(_Ifaddrs)),
    ("ifa_name", ctypes.c_char_p),
    ("ifa_flags", ctypes.c_uint),
    ("ifa_addr", ctypes.POINTER(_Sockaddr)),
    ("ifa_netmask", ctypes.POINTER(_Sockaddr)),
    ("ifa_dstaddr", ctypes.POINTER(_Sockaddr)),
    ("ifa_data", ctypes.c_void_p),
]


def _sockaddr_ipv4(pointer) -> str | None:
    """Read a dotted IPv4 out of a sockaddr, if that is what it holds.

    BSD (and so macOS) puts a one-byte length ahead of the family; Linux starts with the
    family as a native short. Both keep the address itself at offset 4.
    """
    if not pointer:
        return None
    raw = bytes(pointer.contents.bytes)
    family = raw[1] if sys.platform == "darwin" else struct.unpack("=H", raw[:2])[0]
    if family != socket.AF_INET:
        return None
    return socket.inet_ntoa(raw[4:8])


def _posix_addresses() -> list[Interface]:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.getifaddrs.restype = ctypes.c_int
    libc.getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(_Ifaddrs))]
    libc.freeifaddrs.argtypes = [ctypes.POINTER(_Ifaddrs)]

    head = ctypes.POINTER(_Ifaddrs)()
    if libc.getifaddrs(ctypes.byref(head)) != 0:
        return []
    try:
        return list(_walk(head))
    finally:
        libc.freeifaddrs(head)


def _walk(head):
    node = head
    while node:
        entry = node.contents
        address = _sockaddr_ipv4(entry.ifa_addr)
        if address and not entry.ifa_flags & IFF_LOOPBACK:
            yield Interface(
                name=(entry.ifa_name or b"").decode("utf-8", "replace"),
                address=address,
                prefix=_prefix(_sockaddr_ipv4(entry.ifa_netmask)),
                point_to_point=bool(entry.ifa_flags & IFF_POINTOPOINT),
                running=bool(entry.ifa_flags & IFF_UP
                             and entry.ifa_flags & IFF_RUNNING))
        node = entry.ifa_next


def _prefix(netmask: str | None) -> int | None:
    if not netmask:
        return None
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    except ValueError:
        return None


# ---- Windows: ask the resolver ------------------------------------------------------

def _windows_addresses() -> list[Interface]:
    """Windows answers its own host name with every adapter's IPv4 address.

    No flags come back, so nothing here can be ruled out automatically — which is why
    every address is offered to the officer to choose from.
    """
    try:
        info = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    out = []
    for entry in info:
        address = entry[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.is_loopback:
            continue
        out.append(Interface(name="", address=address, prefix=None,
                             point_to_point=False, running=True))
    return out
