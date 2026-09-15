"""State behind the desktop pairing page: the invitation, the QR, and the LAN switch."""
from __future__ import annotations

import io
from datetime import UTC, datetime

from sqlalchemy import func, select

from ..db.models import DeviceEnrollment
from ..net import lan_address
from ..svc.auth import Principal
from ..svc.auth_core import ROLE_PERMISSIONS


class PairingService:
    """Holds the current invitation so the page can be reloaded without minting another.

    An enrollment token is single-use and expires in fifteen minutes. Issuing a fresh one
    on every page render would leave a trail of live tokens behind a browser refresh.
    """

    def __init__(self, accounts, auth, credentials: dict, port: int):
        self.accounts = accounts
        self.auth = auth
        self.credentials = credentials
        self.port = port
        self.network_open = False
        self._invitation: dict | None = None

    # ---- LAN -------------------------------------------------------------------

    def lan_url(self) -> str | None:
        address = lan_address()
        return f"http://{address}:{self.port}" if address else None

    def set_network_open(self, value: bool) -> None:
        self.network_open = bool(value)

    # ---- the invitation --------------------------------------------------------

    def invitation(self) -> dict:
        if self._invitation is None or self._expired(self._invitation):
            return self.new_invitation()
        return self._invitation

    def new_invitation(self) -> dict:
        self._invitation = self.accounts.issue_enrollment(
            self.credentials["officer"]["id"], self.lan_url(), self._admin())
        return self._invitation

    @staticmethod
    def _expired(invitation: dict) -> bool:
        return datetime.fromisoformat(invitation["expires_at"]) <= datetime.now(UTC)

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

        uri = self.invitation()["enrollment_uri"]
        return segno.make(uri, error="m").svg_inline(scale=6, border=2).encode("utf-8")

    def qr_terminal(self) -> str:
        import segno

        out = io.StringIO()
        segno.make(self.invitation()["enrollment_uri"], error="m").terminal(
            out, compact=True, border=2)
        return out.getvalue()

    def snapshot(self) -> dict:
        invitation = self.invitation()
        return {
            "lan_url": self.lan_url(),
            "network_open": self.network_open,
            "fingerprint": invitation["server_fingerprint"],
            "expires_at": invitation["expires_at"],
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
