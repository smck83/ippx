"""Sync client tests against a mocked HTTP layer."""

from __future__ import annotations

import inspect

import httpx
import pytest
import respx

from ippx import AsyncIppClient, IppClient, IppResponseError, JobState, Operation
from ippx._codec import decode

from .helpers import ipp_response

URL = "ipps://printer.local:631/ipp/print"
HTTP_URL = "https://printer.local:631/ipp/print"


@respx.mock
def test_sync_print_job() -> None:
    route = respx.post(HTTP_URL).mock(
        return_value=httpx.Response(200, content=ipp_response(job={"job-id": 9, "job-state": 3}))
    )
    with IppClient(URL) as client:
        job = client.print_job(b"data", document_format="application/pdf")
    assert job.job_id == 9
    assert job.state == JobState.PENDING
    assert decode(route.calls.last.request.content).code == Operation.PRINT_JOB


@respx.mock
def test_sync_error_raises() -> None:
    respx.post(HTTP_URL).mock(return_value=httpx.Response(200, content=ipp_response(status=0x0400)))
    with IppClient(URL) as client, pytest.raises(IppResponseError):
        client.get_printer_attributes()


@respx.mock
def test_sync_wait_for_job() -> None:
    respx.post(HTTP_URL).mock(
        side_effect=[
            httpx.Response(200, content=ipp_response(job={"job-id": 3, "job-state": 5})),
            httpx.Response(200, content=ipp_response(job={"job-id": 3, "job-state": 9})),
        ]
    )
    with IppClient(URL) as client:
        job = client.wait_for_job(3, timeout=5, initial_interval=0.01)
    assert job.state == JobState.COMPLETED


@respx.mock
def test_basic_auth_header_sent() -> None:
    route = respx.post(HTTP_URL).mock(return_value=httpx.Response(200, content=ipp_response()))
    with IppClient(URL, auth=httpx.BasicAuth("scott", "secret")) as client:
        client.validate_job()
    assert route.calls.last.request.headers["Authorization"].startswith("Basic ")


@respx.mock
@pytest.mark.parametrize(
    "method",
    ["get_printer_attributes", "validate_job", "get_jobs"],
)
def test_client_version_sent_on_every_operation(method: str) -> None:
    route = respx.post(HTTP_URL).mock(return_value=httpx.Response(200, content=ipp_response()))
    with IppClient(URL, version=(1, 1)) as client:
        getattr(client, method)()
    assert decode(route.calls.last.request.content).version == (1, 1)


def test_sync_and_async_clients_have_matching_api() -> None:
    """The two clients are maintained by hand; keep their public API in lockstep."""

    def public_methods(cls: type) -> dict[str, inspect.Signature]:
        return {
            name: inspect.signature(member)
            for name, member in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith("_")
        }

    sync_api = public_methods(IppClient)
    async_api = public_methods(AsyncIppClient)
    assert sync_api.keys() == async_api.keys()
    for name, sig in sync_api.items():
        assert sig == async_api[name], f"signature mismatch on {name}"
