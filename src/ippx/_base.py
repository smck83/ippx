"""Shared plumbing between sync and async clients."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ._codec import IppMessage, decode
from ._operations import status_message
from ._tls import TlsConfig
from .exceptions import IppHttpError, IppResponseError

CONTENT_TYPE = "application/ipp"
DEFAULT_PORT = 631
DEFAULT_PATH = "/ipp/print"

_SCHEME_MAP = {"ipps": "https", "ipp": "http", "https": "https", "http": "http"}


def normalise_url(url: str) -> tuple[str, str]:
    """Return (http_url, printer_uri).

    ``http_url`` is what httpx talks to; ``printer_uri`` is the ipp/ipps form
    sent in the printer-uri operation attribute.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _SCHEME_MAP:
        raise ValueError(
            f"unsupported scheme {parts.scheme!r}; use ipps://, ipp://, https:// or http://"
        )
    http_scheme = _SCHEME_MAP[scheme]
    ipp_scheme = "ipps" if http_scheme == "https" else "ipp"
    host = parts.hostname or ""
    if not host:
        raise ValueError(f"no host in URL {url!r}")
    port = parts.port or DEFAULT_PORT
    path = parts.path if parts.path and parts.path != "/" else DEFAULT_PATH
    netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    http_url = urlunsplit((http_scheme, netloc, path, parts.query, ""))
    printer_uri = urlunsplit((ipp_scheme, netloc, path, parts.query, ""))
    return http_url, printer_uri


def httpx_kwargs(
    tls: TlsConfig | None,
    auth: httpx.Auth | tuple[str, str] | None,
    timeout: float | httpx.Timeout,
) -> dict[str, Any]:
    tls = tls or TlsConfig()
    kwargs: dict[str, Any] = {
        "verify": tls.httpx_verify(),
        "timeout": timeout,
        "headers": {"Content-Type": CONTENT_TYPE, "Accept": CONTENT_TYPE},
    }
    if auth is not None:
        kwargs["auth"] = auth
    return kwargs


def check_response(response: httpx.Response) -> IppMessage:
    if response.status_code != 200:
        raise IppHttpError(response.status_code, response.reason_phrase)
    msg = decode(response.content)
    if msg.code >= 0x0100:
        raise IppResponseError(msg.code, status_message(msg))
    return msg
