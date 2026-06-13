"""ippx: sync and async IPP/IPPS client for sending print jobs and
monitoring network printers."""

from httpx import BasicAuth, DigestAuth

from ._async import AsyncIppClient
from ._codec import Attribute, IppMessage, Resolution, Tag, decode, encode
from ._models import Job, JobState, Operation, Printer, PrinterState
from ._sync import IppClient
from ._tls import TlsConfig
from .exceptions import (
    IppDecodeError,
    IppError,
    IppHttpError,
    IppResponseError,
    JobTimeoutError,
)

__version__ = "0.1.0"

__all__ = [
    "AsyncIppClient",
    "Attribute",
    "BasicAuth",
    "DigestAuth",
    "IppClient",
    "IppDecodeError",
    "IppError",
    "IppHttpError",
    "IppMessage",
    "IppResponseError",
    "Job",
    "JobState",
    "JobTimeoutError",
    "Operation",
    "Printer",
    "PrinterState",
    "Resolution",
    "Tag",
    "TlsConfig",
    "decode",
    "encode",
]
