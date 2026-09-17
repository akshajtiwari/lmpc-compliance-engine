"""Optional TLS for the field server: a self-signed certificate the phone pins.

Cleartext HTTP on a private LAN is the preview posture, and the server fingerprint
(TOFU) check detects a substituted server — it does not detect an eavesdropper or a
proxy that forwards the real fingerprint. TLS closes that gap, but only when the phone
pins the certificate: an unmodified React Native fetch rejects a self-signed chain
before any application code runs, so TLS is strictly opt-in and the pin travels in the
same out-of-band channel the QR does.

The pin is the SHA-256 of the certificate's SubjectPublicKeyInfo. A substituted
certificate — however valid its own chain looks — carries a different SPKI and fails
the pin; a passive eavesdropper sees nothing but ciphertext.
"""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
from pathlib import Path


def spki_sha256(cert_path: Path) -> str:
    """The pin value: SHA-256 over the certificate's public key, SPKI DER form."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return hashlib.sha256(cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def ensure_certificate(directory: Path, addresses: list[str] | None = None,
                       common_name: str = "LMPC Compliance") -> dict:
    """Load the self-signed certificate, or generate one that covers `addresses`.

    SubjectAlternativeName carries every address a phone might dial, because a pinning
    client still validates the host name on top of the pin. A regenerated certificate
    (new network, new addresses) is a new pin, which is exactly what a re-minted
    invitation is for.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_path, key_path = directory / "server.pem", directory / "server-key.pem"
    if cert_path.exists() and key_path.exists():
        return {"cert": str(cert_path), "key": str(key_path),
                "tls_pin": spki_sha256(cert_path)}
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names = {x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))}
    for address in addresses or []:
        try:
            names.add(x509.IPAddress(ipaddress.ip_address(address)))
        except ValueError:
            continue
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(list(names)), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    for path in (cert_path, key_path):
        path.chmod(0o600)
    return {"cert": str(cert_path), "key": str(key_path),
            "tls_pin": spki_sha256(cert_path)}


def configured_pin(settings) -> str:
    """The pin a configured certificate carries, or empty when TLS is off."""
    if not (settings.tls_cert and settings.tls_key):
        return ""
    return spki_sha256(Path(settings.tls_cert))