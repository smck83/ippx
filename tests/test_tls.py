"""TLS configuration tests, including a live handshake against a local
TLS server to prove fingerprint pinning accepts the right cert and rejects
the wrong one."""

from __future__ import annotations

import hashlib
import socket
import ssl
import subprocess
import threading
from pathlib import Path

import pytest

from ippx._tls import FingerprintMismatch, TlsConfig, parse_fingerprint


def test_parse_fingerprint_formats() -> None:
    digest = hashlib.sha256(b"cert").hexdigest()
    raw = bytes.fromhex(digest)
    colons = ":".join(digest[i : i + 2] for i in range(0, 64, 2))
    assert parse_fingerprint(digest) == raw
    assert parse_fingerprint(f"sha256:{digest}") == raw
    assert parse_fingerprint(f"SHA256:{colons.upper()}") == raw


def test_parse_fingerprint_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_fingerprint("sha256:zzzz")
    with pytest.raises(ValueError):
        parse_fingerprint("abcd")  # too short


def test_verify_false_context() -> None:
    ctx = TlsConfig(verify=False).httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_verify_true_builds_verifying_context() -> None:
    """verify=True must build an explicit context (not the bare bool) so the
    printer cipher policy applies and genuine cert errors stay truthful."""
    ctx = TlsConfig().httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


@pytest.mark.parametrize(
    "cfg",
    [
        TlsConfig(),
        TlsConfig(verify=False),
        TlsConfig(fingerprint="00" * 32),
    ],
)
def test_built_contexts_offer_rsa_key_exchange(cfg: TlsConfig) -> None:
    """Printers commonly offer only plain-RSA key exchange; every context ippx
    builds must include those suites, which distro-default OpenSSL policy
    (SECLEVEL=2) excludes."""
    ctx = cfg.httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    names = {c["name"] for c in ctx.get_ciphers()}
    assert "AES256-GCM-SHA384" in names  # RSA key exchange, as on HP M283fdw


def test_ciphers_override_respected() -> None:
    ctx = TlsConfig(verify=False, ciphers="ECDHE-RSA-AES256-GCM-SHA384").httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    tls12 = {c["name"] for c in ctx.get_ciphers() if c["protocol"] == "TLSv1.2"}
    assert tls12 == {"ECDHE-RSA-AES256-GCM-SHA384"}


@pytest.fixture(scope="module")
def self_signed_server(tmp_path_factory: pytest.TempPathFactory):
    """A minimal TLS server with a fresh self-signed cert."""
    tmp: Path = tmp_path_factory.mktemp("tls")
    cert = tmp / "cert.pem"
    key = tmp / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    fingerprint = hashlib.sha256(der).hexdigest()

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(cert), str(key))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            try:
                with server_ctx.wrap_socket(conn, server_side=True) as tls_conn:
                    tls_conn.recv(1)
            except ssl.SSLError:
                pass
            except OSError:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield port, fingerprint
    stop.set()
    thread.join(timeout=2)
    listener.close()


def _handshake(port: int, ctx: ssl.SSLContext) -> None:
    with (
        socket.create_connection(("127.0.0.1", port), timeout=5) as sock,
        ctx.wrap_socket(sock, server_hostname="localhost") as tls,
    ):
        tls.send(b"x")


def test_pin_accepts_matching_cert(self_signed_server: tuple[int, str]) -> None:
    port, fingerprint = self_signed_server
    ctx = TlsConfig(fingerprint=f"sha256:{fingerprint}").httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    _handshake(port, ctx)  # must not raise


def test_pin_rejects_wrong_cert(self_signed_server: tuple[int, str]) -> None:
    port, _ = self_signed_server
    wrong = hashlib.sha256(b"not the cert").hexdigest()
    ctx = TlsConfig(fingerprint=f"sha256:{wrong}").httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    with pytest.raises(FingerprintMismatch):
        _handshake(port, ctx)


def test_verify_true_reports_cert_error_not_handshake_failure(
    self_signed_server: tuple[int, str],
) -> None:
    """Against a self-signed cert, verify=True should fail with a certificate
    verification error, not a cipher/handshake-failure alert."""
    port, _ = self_signed_server
    ctx = TlsConfig().httpx_verify()
    assert isinstance(ctx, ssl.SSLContext)
    with pytest.raises(ssl.SSLCertVerificationError):
        _handshake(port, ctx)
