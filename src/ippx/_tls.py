"""TLS configuration: system CA, custom CA bundle, fingerprint pinning, or off.

Fingerprint pinning is implemented with an ``ssl.SSLContext`` whose socket and
object classes verify the peer certificate's SHA-256 digest immediately after
the handshake completes. This works for both sync (``SSLSocket``) and async
(``SSLObject``) httpx transports with no TOCTOU window.
"""

from __future__ import annotations

import hashlib
import ssl
from dataclasses import dataclass

# Printers very commonly offer only plain-RSA key exchange (no ECDHE/DHE),
# which OpenSSL rejects at the distro-default security level 2 with a bare
# handshake-failure alert -- before certificate validation even runs, so the
# user sees a confusing cipher error instead of the real cause. Level 1 still
# excludes export/null/anonymous ciphers and keys under 1024 bits, but lets
# RSA key exchange through so real printer hardware is reachable and any cert
# problem surfaces as a truthful certificate error. Applied to every context
# ippx builds, including the default verify=True path. TLS 1.3 suites are
# configured separately by OpenSSL and are unaffected by this string.
_PRINTER_CIPHERS = "DEFAULT:@SECLEVEL=1"


@dataclass
class TlsConfig:
    """TLS behaviour for ipps:// connections.

    verify:
        ``True`` validates against system CAs (default), with a cipher policy
        relaxed enough to complete a handshake with printers that only offer
        plain-RSA key exchange (see ``ciphers``). A string is treated as a
        path to a CA bundle (PEM); note that in this mode hostname
        verification is disabled, because printers are usually addressed by
        IP or an internal name that does not match the certificate, so the CA
        bundle itself is the trust anchor and any certificate issued by that
        CA is accepted. ``False`` disables verification entirely, which is
        common for printers with self-signed certificates; prefer
        ``fingerprint`` pinning over this where possible.
    fingerprint:
        Pin the server certificate by SHA-256 digest of the DER certificate,
        e.g. ``"sha256:AB:CD:..."`` or bare hex. When set, ``verify`` is
        ignored and the connection fails unless the digest matches exactly.
    client_cert:
        Path to a PEM client certificate, or a ``(cert_path, key_path)`` tuple,
        for mutual TLS.
    ciphers:
        OpenSSL cipher string for every context ippx builds. Defaults to
        ``"DEFAULT:@SECLEVEL=1"`` because printers very commonly offer only
        plain-RSA key exchange, which stock OpenSSL policy (level 2) rejects.
        Set e.g. ``"ALL:@SECLEVEL=0"`` for ancient devices, or a stricter
        string such as ``"DEFAULT:@SECLEVEL=2"`` to enforce full default
        policy.
    """

    verify: bool | str = True
    fingerprint: str | None = None
    client_cert: str | tuple[str, str] | None = None
    ciphers: str | None = _PRINTER_CIPHERS

    def httpx_verify(self) -> bool | str | ssl.SSLContext:
        if self.fingerprint:
            ctx = _pinned_context(parse_fingerprint(self.fingerprint))
            return self._finish(ctx)
        if isinstance(self.verify, str):
            ctx = ssl.create_default_context(cafile=self.verify)
            # printers are nearly always addressed by IP or internal name that
            # will not match the cert; the CA pin is the trust anchor here
            ctx.check_hostname = False
            return self._finish(ctx)
        if self.verify is False:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return self._finish(ctx)
        # verify is True: build an explicit default-trust context rather than
        # returning the bare bool, so the printer cipher policy applies and a
        # genuine cert problem (self-signed, expired) surfaces as a truthful
        # certificate error instead of a handshake-failure alert.
        ctx = ssl.create_default_context()
        return self._finish(ctx)

    def _finish(self, ctx: ssl.SSLContext) -> ssl.SSLContext:
        if self.ciphers:
            ctx.set_ciphers(self.ciphers)
        if self.client_cert is not None:
            if isinstance(self.client_cert, tuple):
                ctx.load_cert_chain(self.client_cert[0], self.client_cert[1])
            else:
                ctx.load_cert_chain(self.client_cert)
        return ctx


def parse_fingerprint(value: str) -> bytes:
    """Parse 'sha256:AA:BB:...' / 'sha256:aabb...' / bare hex into raw bytes."""
    cleaned = value.strip().lower()
    if cleaned.startswith("sha256:"):
        cleaned = cleaned[len("sha256:") :]
    cleaned = cleaned.replace(":", "").replace(" ", "")
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid certificate fingerprint: {value!r}") from exc
    if len(raw) != 32:
        raise ValueError(f"fingerprint must be a SHA-256 digest (32 bytes), got {len(raw)} bytes")
    return raw


class FingerprintMismatch(ssl.SSLCertVerificationError):
    """Raised when the server certificate does not match the pinned digest."""


def _check_pin(expected: bytes, der_cert: bytes | None) -> None:
    if der_cert is None:
        raise FingerprintMismatch("no peer certificate to verify against pin")
    actual = hashlib.sha256(der_cert).digest()
    if actual != expected:
        raise FingerprintMismatch(
            f"certificate fingerprint mismatch: expected sha256:{expected.hex()}, "
            f"got sha256:{actual.hex()}"
        )


def _pinned_context(expected: bytes) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    class _PinnedSocket(ssl.SSLSocket):
        def do_handshake(self, *args: object, **kwargs: object) -> None:
            super().do_handshake(*args, **kwargs)  # type: ignore[arg-type]
            _check_pin(expected, self.getpeercert(binary_form=True))

    class _PinnedObject(ssl.SSLObject):
        def do_handshake(self) -> None:
            super().do_handshake()
            _check_pin(expected, self.getpeercert(binary_form=True))

    ctx.sslsocket_class = _PinnedSocket
    ctx.sslobject_class = _PinnedObject
    return ctx
