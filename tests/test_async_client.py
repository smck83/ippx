"""Async client tests against a mocked HTTP layer."""

from __future__ import annotations

import httpx
import pytest
import respx

from ippx import (
    AsyncIppClient,
    IppHttpError,
    IppResponseError,
    JobState,
    JobTimeoutError,
    Operation,
    PrinterState,
)
from ippx._codec import decode

from .helpers import ipp_response

URL = "ipps://printer.local:631/ipp/print"
HTTP_URL = "https://printer.local:631/ipp/print"


@respx.mock
async def test_print_job_success() -> None:
    route = respx.post(HTTP_URL).mock(
        return_value=httpx.Response(
            200,
            content=ipp_response(
                job={"job-id": 42, "job-state": 3, "job-uri": "ipps://printer.local:631/jobs/42"}
            ),
            headers={"Content-Type": "application/ipp"},
        )
    )
    async with AsyncIppClient(URL, requesting_user_name="scott") as client:
        job = await client.print_job(
            b"%PDF-1.7", document_format="application/pdf", job_name="invoice"
        )
    assert job.job_id == 42
    assert job.state == JobState.PENDING

    sent = decode(route.calls.last.request.content)
    assert sent.code == Operation.PRINT_JOB
    op = {a.name: a.values for a in sent.groups[0][1]}
    assert op["printer-uri"] == [URL]
    assert op["requesting-user-name"] == ["scott"]
    assert op["document-format"] == ["application/pdf"]
    assert sent.data == b"%PDF-1.7"
    assert route.calls.last.request.headers["Content-Type"] == "application/ipp"


@respx.mock
async def test_get_printer_attributes() -> None:
    respx.post(HTTP_URL).mock(
        return_value=httpx.Response(
            200,
            content=ipp_response(
                printer={
                    "printer-name": "HP M283fdw",
                    "printer-state": 3,
                    "printer-is-accepting-jobs": True,
                    "printer-state-reasons": ["none"],
                    "document-format-supported": ["application/pdf", "image/urf"],
                    "operations-supported": [0x0002, 0x000B],
                }
            ),
        )
    )
    async with AsyncIppClient(URL) as client:
        printer = await client.get_printer_attributes()
    assert printer.name == "HP M283fdw"
    assert printer.state == PrinterState.IDLE
    assert printer.is_accepting_jobs is True
    assert printer.supports_format("application/pdf")
    assert printer.supports_operation(Operation.PRINT_JOB)


@respx.mock
async def test_ipp_error_status_raises() -> None:
    respx.post(HTTP_URL).mock(
        return_value=httpx.Response(
            200, content=ipp_response(status=0x0506, status_msg="not accepting jobs")
        )
    )
    async with AsyncIppClient(URL) as client:
        with pytest.raises(IppResponseError) as exc_info:
            await client.print_job(b"x")
    assert exc_info.value.status_code == 0x0506
    assert exc_info.value.status_name == "server-error-not-accepting-jobs"
    assert "not accepting jobs" in str(exc_info.value)


@respx.mock
async def test_http_error_raises() -> None:
    respx.post(HTTP_URL).mock(return_value=httpx.Response(401))
    async with AsyncIppClient(URL) as client:
        with pytest.raises(IppHttpError) as exc_info:
            await client.get_printer_attributes()
    assert exc_info.value.status_code == 401


@respx.mock
async def test_get_jobs_multiple_groups() -> None:
    respx.post(HTTP_URL).mock(
        return_value=httpx.Response(
            200,
            content=ipp_response(
                jobs=[
                    {"job-id": 1, "job-state": 9},
                    {"job-id": 2, "job-state": 5},
                ]
            ),
        )
    )
    async with AsyncIppClient(URL) as client:
        jobs = await client.get_jobs(which_jobs="completed")
    assert [j.job_id for j in jobs] == [1, 2]
    assert jobs[1].state == JobState.PROCESSING


@respx.mock
async def test_wait_for_job_polls_until_terminal() -> None:
    responses = [
        httpx.Response(200, content=ipp_response(job={"job-id": 7, "job-state": 5})),
        httpx.Response(200, content=ipp_response(job={"job-id": 7, "job-state": 5})),
        httpx.Response(
            200,
            content=ipp_response(
                job={
                    "job-id": 7,
                    "job-state": 9,
                    "job-state-reasons": ["job-completed-successfully"],
                }
            ),
        ),
    ]
    route = respx.post(HTTP_URL).mock(side_effect=responses)
    async with AsyncIppClient(URL) as client:
        job = await client.wait_for_job(7, timeout=10, initial_interval=0.01)
    assert job.state == JobState.COMPLETED
    assert "job-completed-successfully" in job.state_reasons
    assert route.call_count == 3


@respx.mock
async def test_wait_for_job_timeout() -> None:
    respx.post(HTTP_URL).mock(
        return_value=httpx.Response(200, content=ipp_response(job={"job-id": 7, "job-state": 5}))
    )
    async with AsyncIppClient(URL) as client:
        with pytest.raises(JobTimeoutError) as exc_info:
            await client.wait_for_job(7, timeout=0.05, initial_interval=0.01)
    assert exc_info.value.job_id == 7
    assert exc_info.value.last_state == JobState.PROCESSING


@respx.mock
async def test_cancel_and_validate() -> None:
    route = respx.post(HTTP_URL).mock(return_value=httpx.Response(200, content=ipp_response()))
    async with AsyncIppClient(URL) as client:
        await client.validate_job(document_format="application/pdf")
        await client.cancel_job(5)
    first = decode(route.calls[0].request.content)
    second = decode(route.calls[1].request.content)
    assert first.code == Operation.VALIDATE_JOB
    assert second.code == Operation.CANCEL_JOB
    op = {a.name: a.values for a in second.groups[0][1]}
    assert op["job-id"] == [5]
