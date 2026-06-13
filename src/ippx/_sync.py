"""Synchronous IPP/IPPS client. Mirrors AsyncIppClient method for method."""

from __future__ import annotations

import time
from itertools import count
from types import TracebackType
from typing import Any

import httpx

from . import _operations as ops
from ._base import check_response, httpx_kwargs, normalise_url
from ._codec import Attribute, IppMessage, Tag, encode
from ._models import Job, Printer
from ._tls import TlsConfig
from .exceptions import JobTimeoutError


class IppClient:
    """Sync client for a single IPP/IPPS printer endpoint.

    Usage::

        with IppClient("ipps://printer.example.com:631/ipp/print") as printer:
            job = printer.print_job(pdf_bytes, document_format="application/pdf")
            printer.wait_for_job(job.job_id, timeout=120)
    """

    def __init__(
        self,
        url: str,
        *,
        auth: httpx.Auth | tuple[str, str] | None = None,
        tls: TlsConfig | None = None,
        timeout: float | httpx.Timeout = 30.0,
        requesting_user_name: str | None = "ippx",
        version: tuple[int, int] = ops.DEFAULT_VERSION,
    ) -> None:
        self._http_url, self.printer_uri = normalise_url(url)
        self.requesting_user_name = requesting_user_name
        self.version = version
        self._request_ids = count(1)
        self._http = httpx.Client(**httpx_kwargs(tls, auth, timeout))

    def __enter__(self) -> IppClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _send(self, msg: IppMessage) -> IppMessage:
        response = self._http.post(self._http_url, content=encode(msg))
        return check_response(response)

    def get_printer_attributes(self, requested_attributes: list[str] | None = None) -> Printer:
        msg = ops.get_printer_attributes_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            requesting_user_name=self.requesting_user_name,
            requested_attributes=requested_attributes,
            version=self.version,
        )
        resp = self._send(msg)
        return ops.parse_printer(ops.first_group(resp, Tag.PRINTER_ATTRS))

    def validate_job(
        self,
        *,
        document_format: str = "application/octet-stream",
        job_attributes: dict[str, Any] | list[Attribute] | None = None,
    ) -> None:
        msg = ops.validate_job_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            document_format=document_format,
            requesting_user_name=self.requesting_user_name,
            job_attributes=job_attributes,
            version=self.version,
        )
        self._send(msg)

    def print_job(
        self,
        document: bytes,
        *,
        document_format: str = "application/octet-stream",
        job_name: str | None = None,
        job_attributes: dict[str, Any] | list[Attribute] | None = None,
    ) -> Job:
        msg = ops.print_job_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            document=document,
            document_format=document_format,
            job_name=job_name,
            requesting_user_name=self.requesting_user_name,
            job_attributes=job_attributes,
            version=self.version,
        )
        resp = self._send(msg)
        return ops.parse_job(ops.first_group(resp, Tag.JOB_ATTRS))

    def get_job_attributes(self, job_id: int, requested_attributes: list[str] | None = None) -> Job:
        msg = ops.get_job_attributes_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            job_id=job_id,
            requesting_user_name=self.requesting_user_name,
            requested_attributes=requested_attributes,
            version=self.version,
        )
        resp = self._send(msg)
        return ops.parse_job(ops.first_group(resp, Tag.JOB_ATTRS))

    def cancel_job(self, job_id: int) -> None:
        msg = ops.cancel_job_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            job_id=job_id,
            requesting_user_name=self.requesting_user_name,
            version=self.version,
        )
        self._send(msg)

    def get_jobs(
        self,
        *,
        which_jobs: str = "not-completed",
        my_jobs: bool = False,
        limit: int | None = None,
        requested_attributes: list[str] | None = None,
    ) -> list[Job]:
        msg = ops.get_jobs_request(
            printer_uri=self.printer_uri,
            request_id=next(self._request_ids),
            requesting_user_name=self.requesting_user_name,
            which_jobs=which_jobs,
            my_jobs=my_jobs,
            limit=limit,
            requested_attributes=requested_attributes,
            version=self.version,
        )
        resp = self._send(msg)
        return [ops.parse_job(g) for g in ops.all_groups(resp, Tag.JOB_ATTRS)]

    def wait_for_job(
        self,
        job_id: int,
        *,
        timeout: float = 300.0,
        initial_interval: float = 1.0,
        max_interval: float = 15.0,
    ) -> Job:
        """Poll Get-Job-Attributes with exponential backoff until the job
        reaches a terminal state (completed, canceled, aborted).

        Raises JobTimeoutError if the deadline passes first."""
        deadline = time.monotonic() + timeout
        interval = initial_interval
        job = self.get_job_attributes(job_id, ["job-state", "job-state-reasons"])
        while not job.is_terminal:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobTimeoutError(job_id, timeout, job.state)
            time.sleep(min(interval, remaining))
            interval = min(interval * 2, max_interval)
            job = self.get_job_attributes(job_id, ["job-state", "job-state-reasons"])
        return job
