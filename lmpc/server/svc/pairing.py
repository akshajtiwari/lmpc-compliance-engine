"""State behind the desktop pairing page: the invitation, the QR, and the LAN switch.

The address in the QR is the whole game. A code that carries an address the phone cannot
dial fails identically to a code that is not there at all — the phone says it "could not
reach the local server from this network" and the officer concludes the two are on
different networks. So the address is chosen, not guessed: ranked candidates with a
reason attached, an override for a server reached from somewhere else entirely, and a
record of who has actually reached this machine.
"""
from __future__ import annotations

import io
from datetime import UTC, datetime

from sqlalchemy import func, select

from ..db.models import DeviceEnrollment
from ..net import Candidate, best_address, lan_candidates, normalise_base_url
from ..svc.auth import Principal
from ..svc.auth_core import ROLE_PERMISSIONS


class PairingService:
    """Holds the current invitation so the page can be reloaded without minting another.

    An enrollment token is single-use and expires in fifteen minutes. Issuing a fresh one
    on every page render would leave a trail of live tokens behind a browser refresh.
    """

    def __init__(self, accounts, auth, credentials: dict, port: int, *,
                 advertised: str = "", network_open: bool = False):
        self.accounts = accounts
        self.auth = auth
        self.credentials = credentials
        self.port = port
        self.network_open = bool(network_open)
        self._advertised = normalise_base_url(advertised, default_port=port) \
            if advertised else ""
        self._invitation: dict | None = None
        self._last_contact: tuple[datetime, str, bool] | None = None

    # ---- where the phone should dial -------------------------------------------

    def candidates(self) -> list[Candidate]:
        return lan_candidates()

    def advertised_url(self) -> str | None:
        """The base URL the QR carries, or None when there is nothing to advertise."""
        if self._advertised:
            return self._advertised
        configured = getattr(self.auth.settings, "public_base_url", "")
        if configured:
            return configured.rstrip("/")
        address = best_address()
        return f"http://{address}:{self.port}" if address else None

    def set_advertised(self, value: str) -> str:
        """Point the QR at a different address, and mint a code that carries it.

        Re-minting is the point: a stale invitation would keep handing out the old
        address, so the officer would fix the setting and watch the phone fail anyway.
        """
        self._advertised = normalise_base_url(value, default_port=self.port)
        self.new_invitation()
        return self._advertised

    def clear_advertised(self) -> None:
        self._advertised = ""
        self.new_invitation()

    @property
    def overridden(self) -> bool:
        return bool(self._advertised)

    # keeps `server/run.py` and the desktop banner working off one notion of "the address"
    def lan_url(self) -> str | None:
        return self.advertised_url()

    # ---- the LAN switch and what has reached us --------------------------------

    def set_network_open(self, value: bool) -> None:
        self.network_open = bool(value)

    def note_contact(self, peer: str, allowed: bool) -> None:
        """Record that something off this machine reached us, refused or not.

        A refused contact is the single most useful thing the page can say: it means the
        phone found the right address and the switch is the only thing in the way.
        """
        self._last_contact = (datetime.now(UTC), peer, allowed)

    def last_contact(self) -> dict | None:
        if self._last_contact is None:
            return None
        when, peer, allowed = self._last_contact
        return {"seconds_ago": max(0, int((datetime.now(UTC) - when).total_seconds())),
                "peer": peer, "allowed": allowed}

    # ---- the invitation --------------------------------------------------------

    def invitation(self) -> dict | None:
        """The live invitation, or None when there is no address to put in one.

        A machine with its Wi-Fi off has nothing to advertise. Minting anyway raises, and
        the page that would have let the officer type an address never renders — so the
        one screen that could fix the problem is the one the problem takes down.
        """
        if self.advertised_url() is None:
            return None
        if self._invitation is None or self._stale(self._invitation):
            return self.new_invitation()
        return self._invitation

    def new_invitation(self) -> dict | None:
        advertised = self.advertised_url()
        if advertised is None:
            self._invitation = None
            return None
        self._invitation = self.accounts.issue_enrollment(
            self.credentials["officer"]["id"], advertised, self._admin())
        return self._invitation

    def _stale(self, invitation: dict) -> bool:
        """Expired, or minted for an address we would no longer advertise.

        Wi-Fi changes under a running server. Without this an officer who joins the right
        network still scans a code pointing at the network they left.
        """
        if datetime.fromisoformat(invitation["expires_at"]) <= datetime.now(UTC):
            return True
        return invitation.get("server_url") != self.advertised_url()

    def _admin(self) -> Principal:
        """The seeded supervisor, acting on behalf of somebody sitting at the machine.

        The pairing page is already loopback-only and CSRF-protected, so this does not
        widen access; it names an accountable actor in the audit log instead of writing
        an anonymous one."""
        admin = self.credentials["admin"]
        return Principal(
            id=admin["id"], full_name="Supervisor", email=admin["email"], role="ADMIN",
            jurisdiction_id=self.credentials["jurisdiction_id"],
            is_legal_reviewer=True, permissions=frozenset(ROLE_PERMISSIONS["ADMIN"]))

    # ---- rendering -------------------------------------------------------------

    def qr_svg(self) -> bytes:
        # Imported here, not at module scope: the pairing page is mounted only by the
        # desktop build, and a departmental deployment that never shows it should not
        # fail to start for want of a QR library.
        import segno

        return segno.make(self._uri(), error="m").svg_inline(
            scale=6, border=2).encode("utf-8")

    def qr_terminal(self) -> str:
        import segno

        out = io.StringIO()
        segno.make(self._uri(), error="m").terminal(out, compact=True, border=2)
        return out.getvalue()

    def _uri(self) -> str:
        invitation = self.invitation()
        if invitation is None:
            raise ValueError("there is no address to put in a code yet")
        return invitation["enrollment_uri"]

    def snapshot(self) -> dict:
        invitation = self.invitation() or {}
        return {
            "lan_url": self.advertised_url(),
            "advertised_url": self.advertised_url(),
            "overridden": self.overridden,
            "candidates": self.candidates(),
            "network_open": self.network_open,
            "last_contact": self.last_contact(),
            "fingerprint": invitation.get("server_fingerprint",
                                          self.auth.server_fingerprint()),
            "expires_at": invitation.get("expires_at", ""),
            "officer_email": self.credentials["officer"]["email"],
            "officer_password": self.credentials["officer"]["password"],
            "supervisor_email": self.credentials["admin"]["email"],
            "supervisor_password": self.credentials["admin"]["password"],
            "devices_enrolled": self._enrolled(),
        }

    def _enrolled(self) -> int:
        if self.auth.sessions is None:
            return 0
        with self.auth.sessions() as session:
            return int(session.scalar(select(func.count()).select_from(DeviceEnrollment)
                                      .where(DeviceEnrollment.used_at.is_not(None))) or 0)
