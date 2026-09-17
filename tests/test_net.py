"""Which address the phone is told to dial.

The published preview failed here and nowhere else: the QR carried an address the phone
could not reach, the app said it "could not reach the local server from this network",
and that reads to an officer as the two devices being on different networks. These tests
pin the ranking that decides the address, because the failure is silent — a wrong address
produces a perfectly valid QR code.
"""
from __future__ import annotations

import pytest

from lmpc.server import net
from lmpc.server.ifaces import Interface

WIFI = Interface("wlan0", "192.168.1.20", 24, point_to_point=False, running=True)
WARP = Interface("CloudflareWARP", "172.16.0.2", 32, point_to_point=True, running=True)
DOCKER = Interface("docker0", "172.17.0.1", 16, point_to_point=False, running=False)
BRIDGE = Interface("br-a756bbdaa6", "172.21.0.1", 16, point_to_point=False, running=False)
ETHERNET = Interface("enp0s20", "172.16.33.90", 16, point_to_point=False, running=True)
PUBLIC = Interface("eth0", "93.184.216.34", 24, point_to_point=False, running=True)


def interfaces(monkeypatch, found, routed):
    monkeypatch.setattr(net, "enumerate_ipv4", lambda: list(found))
    monkeypatch.setattr(net, "routed_address", lambda: routed)


def test_a_vpn_does_not_get_to_speak_for_the_machine(monkeypatch):
    """The bug, exactly as it shipped.

    CloudflareWARP takes the default route, so asking the routing table which interface
    leaves this machine answers with a point-to-point /32 that belongs to this machine
    alone. Every phone dialling it fails, and the officer is told nothing useful.
    """
    interfaces(monkeypatch, [ETHERNET, WARP, DOCKER], routed="172.16.0.2")
    assert net.lan_address() == "172.16.33.90"
    assert net.best_address() == "172.16.33.90"

    ranked = net.lan_candidates()
    assert [item.host for item in ranked][0] == "172.16.33.90"
    tunnel = next(item for item in ranked if item.host == "172.16.0.2")
    assert tunnel.kind == "tunnel" and not tunnel.usable
    assert tunnel.routed, "the tunnel is still reported as the routed address"


def test_container_bridges_are_never_offered(monkeypatch):
    """They are up, they are private, and nothing outside this computer reaches them."""
    interfaces(monkeypatch, [DOCKER, BRIDGE, WIFI], routed="192.168.1.20")
    assert net.lan_address() == "192.168.1.20"
    assert [item.host for item in net.lan_candidates() if item.usable] == ["192.168.1.20"]


def test_a_public_address_is_offered_but_ranked_below_the_lan(monkeypatch):
    """A server at a remote location may hold only a public address; a laptop on Wi-Fi
    holds both, and there the LAN address is the one the phone in the room should use."""
    interfaces(monkeypatch, [PUBLIC, WIFI], routed="93.184.216.34")
    assert [item.host for item in net.lan_candidates()] == ["192.168.1.20", "93.184.216.34"]
    assert net.lan_address() == "192.168.1.20", "lan_address stays private-only"

    interfaces(monkeypatch, [PUBLIC], routed="93.184.216.34")
    assert net.lan_address() is None
    assert net.best_address() == "93.184.216.34", "a public host is still reachable"


def test_a_machine_with_nothing_usable_says_so(monkeypatch):
    interfaces(monkeypatch, [WARP, DOCKER], routed="172.16.0.2")
    assert net.lan_address() is None
    assert net.best_address() is None
    assert net.lan_candidates(), "the unusable addresses are still listed, with reasons"


def test_enumeration_failing_falls_back_to_the_routing_table(monkeypatch):
    """getifaddrs is not available everywhere. One address beats none."""
    interfaces(monkeypatch, [], routed="192.168.8.4")
    assert net.lan_address() == "192.168.8.4"

    interfaces(monkeypatch, [], routed=None)
    assert net.lan_candidates() == []


def test_every_candidate_carries_a_reason(monkeypatch):
    """The page shows these to a human who is trying to work out why pairing failed."""
    interfaces(monkeypatch, [ETHERNET, WARP, DOCKER, PUBLIC], routed="172.16.0.2")
    for item in net.lan_candidates():
        assert item.note.strip().endswith("."), item
        assert item.kind in ("lan", "public", "tunnel", "virtual", "inactive")


def test_a_candidate_renders_the_url_the_app_will_be_given(monkeypatch):
    interfaces(monkeypatch, [WIFI], routed="192.168.1.20")
    assert net.lan_candidates()[0].url(8000) == "http://192.168.1.20:8000"


# ---- the address an officer types ---------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("192.168.1.20", "http://192.168.1.20:8000"),
    ("192.168.1.20:9000", "http://192.168.1.20:9000"),
    ("https://lmpc.example.gov.in", "https://lmpc.example.gov.in"),
    ("https://lmpc.example.gov.in/", "https://lmpc.example.gov.in"),
    ("http://10.0.0.4:8000", "http://10.0.0.4:8000"),
    ("  10.0.0.4  ", "http://10.0.0.4:8000"),
])
def test_addresses_an_officer_may_type(value, expected):
    assert net.normalise_base_url(value, default_port=8000) == expected


@pytest.mark.parametrize("value", [
    "", "   ",
    "ftp://10.0.0.4",
    "http://10.0.0.4/api",             # apps/mobile/src/api.ts refuses a path
    "http://10.0.0.4?x=1",
    "http://10.0.0.4#top",
    "http://user:pw@10.0.0.4",
    "http://10.0.0.4:notaport",
])
def test_addresses_the_app_would_refuse_are_refused_here(value):
    """Refuse on the page, where it can be corrected — not on a phone that has already
    scanned the code. These are the exact rules in apps/mobile/src/api.ts."""
    with pytest.raises(ValueError):
        net.normalise_base_url(value, default_port=8000)


def test_a_typed_http_url_keeps_the_port_it_was_given():
    """Only a bare host gets this server's port filled in; a full URL is taken as meant,
    so a tunnel on 443 is not rewritten to 8000."""
    assert net.normalise_base_url("http://example.test", default_port=8000) \
        == "http://example.test"


def test_loopback_detection_still_holds():
    assert net.is_loopback("127.0.0.1") and net.is_loopback("::1")
    assert net.is_loopback("localhost") and net.is_loopback("127.0.0.53")
    assert not net.is_loopback("192.168.1.20")
    assert not net.is_loopback(None) and not net.is_loopback("")
