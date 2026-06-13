"""Request builder and URL normalisation tests."""

from __future__ import annotations

import pytest

from ippx import Operation, Tag
from ippx._base import normalise_url
from ippx._operations import print_job_request

URI = "ipps://printer.local:631/ipp/print"


def test_print_job_attribute_order() -> None:
    msg = print_job_request(
        printer_uri=URI,
        request_id=1,
        document=b"data",
        document_format="application/pdf",
        job_name="test",
        requesting_user_name="scott",
        job_attributes=None,
    )
    names = [a.name for a in msg.groups[0][1]]
    # RFC 8011 4.1.4: charset first, natural-language second
    assert names[0] == "attributes-charset"
    assert names[1] == "attributes-natural-language"
    assert "printer-uri" in names
    assert msg.data == b"data"


def test_job_attribute_tag_inference() -> None:
    msg = print_job_request(
        printer_uri=URI,
        request_id=1,
        document=b"x",
        document_format="application/pdf",
        job_name=None,
        requesting_user_name=None,
        job_attributes={"copies": 2, "sides": "two-sided-long-edge", "fit-to-page": True},
    )
    job_group = dict(msg.groups)[Tag.JOB_ATTRS]
    by_name = {a.name: a for a in job_group}
    assert by_name["copies"].tag == Tag.INTEGER
    assert by_name["sides"].tag == Tag.KEYWORD
    assert by_name["fit-to-page"].tag == Tag.BOOLEAN


@pytest.mark.parametrize(
    ("url", "http_url", "printer_uri"),
    [
        (
            "ipps://printer.local:631/ipp/print",
            "https://printer.local:631/ipp/print",
            "ipps://printer.local:631/ipp/print",
        ),
        (
            "ipps://203.0.113.10",
            "https://203.0.113.10:631/ipp/print",
            "ipps://203.0.113.10:631/ipp/print",
        ),
        (
            "ipp://printer.local/ipp/print",
            "http://printer.local:631/ipp/print",
            "ipp://printer.local:631/ipp/print",
        ),
        (
            "https://printer.example.com:8443/ipp/print",
            "https://printer.example.com:8443/ipp/print",
            "ipps://printer.example.com:8443/ipp/print",
        ),
    ],
)
def test_normalise_url(url: str, http_url: str, printer_uri: str) -> None:
    assert normalise_url(url) == (http_url, printer_uri)


def test_normalise_url_rejects_bad_scheme() -> None:
    with pytest.raises(ValueError, match="unsupported scheme"):
        normalise_url("ftp://printer.local")


def test_operation_enum_covers_registry_codes() -> None:
    """Spot-check IANA IPP operation codes that real printers advertise,
    including ones beyond the RFC 8011 required set."""
    assert Operation(0x0002) is Operation.PRINT_JOB
    assert Operation(0x0003) is Operation.PRINT_URI
    assert Operation(0x0007) is Operation.SEND_URI
    assert Operation(0x003B) is Operation.CLOSE_JOB
    assert Operation(0x003C) is Operation.IDENTIFY_PRINTER
    # the HP M283fdw operations-supported set decodes fully to names
    m283 = [2, 3, 4, 5, 6, 7, 59, 8, 9, 10, 11, 60]
    assert all(isinstance(Operation(code), Operation) for code in m283)
