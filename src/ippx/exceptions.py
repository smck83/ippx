"""ippx exception hierarchy."""

from __future__ import annotations

STATUS_NAMES: dict[int, str] = {
    0x0000: "successful-ok",
    0x0001: "successful-ok-ignored-or-substituted-attributes",
    0x0002: "successful-ok-conflicting-attributes",
    0x0400: "client-error-bad-request",
    0x0401: "client-error-forbidden",
    0x0402: "client-error-not-authenticated",
    0x0403: "client-error-not-authorized",
    0x0404: "client-error-not-possible",
    0x0405: "client-error-timeout",
    0x0406: "client-error-not-found",
    0x0407: "client-error-gone",
    0x0408: "client-error-request-entity-too-large",
    0x0409: "client-error-request-value-too-long",
    0x040A: "client-error-document-format-not-supported",
    0x040B: "client-error-attributes-or-values-not-supported",
    0x040C: "client-error-uri-scheme-not-supported",
    0x040D: "client-error-charset-not-supported",
    0x040E: "client-error-conflicting-attributes",
    0x040F: "client-error-compression-not-supported",
    0x0410: "client-error-compression-error",
    0x0411: "client-error-document-format-error",
    0x0412: "client-error-document-access-error",
    0x0500: "server-error-internal-error",
    0x0501: "server-error-operation-not-supported",
    0x0502: "server-error-service-unavailable",
    0x0503: "server-error-version-not-supported",
    0x0504: "server-error-device-error",
    0x0505: "server-error-temporary-error",
    0x0506: "server-error-not-accepting-jobs",
    0x0507: "server-error-busy",
    0x0508: "server-error-job-canceled",
    0x0509: "server-error-multiple-document-jobs-not-supported",
}


class IppError(Exception):
    """Base class for all ippx errors."""


class IppDecodeError(IppError):
    """The printer returned bytes that are not a valid IPP message."""


class IppHttpError(IppError):
    """The HTTP layer failed (non-200 response)."""

    def __init__(self, status_code: int, reason: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} {reason}".rstrip())


class IppResponseError(IppError):
    """The printer returned an IPP error status-code."""

    def __init__(self, status_code: int, status_message: str | None = None) -> None:
        self.status_code = status_code
        self.status_name = STATUS_NAMES.get(status_code, f"0x{status_code:04X}")
        self.status_message = status_message
        detail = f": {status_message}" if status_message else ""
        super().__init__(f"{self.status_name} (0x{status_code:04X}){detail}")


class JobTimeoutError(IppError, TimeoutError):
    """wait_for_job exceeded its timeout before the job reached a terminal state."""

    def __init__(self, job_id: int, timeout: float, last_state: object) -> None:
        self.job_id = job_id
        self.last_state = last_state
        super().__init__(
            f"job {job_id} did not reach a terminal state within {timeout}s "
            f"(last state: {last_state})"
        )
