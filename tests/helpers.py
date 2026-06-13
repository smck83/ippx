"""Helpers shared by client tests: build encoded IPP responses."""

from __future__ import annotations

from typing import Any

from ippx import Attribute, IppMessage, Tag, encode

_TAG_FOR: dict[str, Tag] = {
    "job-id": Tag.INTEGER,
    "job-state": Tag.ENUM,
    "job-state-reasons": Tag.KEYWORD,
    "job-uri": Tag.URI,
    "job-name": Tag.NAME,
    "printer-name": Tag.NAME,
    "printer-state": Tag.ENUM,
    "printer-state-reasons": Tag.KEYWORD,
    "printer-is-accepting-jobs": Tag.BOOLEAN,
    "printer-make-and-model": Tag.TEXT,
    "document-format-supported": Tag.MIME_TYPE,
    "operations-supported": Tag.ENUM,
    "status-message": Tag.TEXT,
}


def _attrs(d: dict[str, Any]) -> list[Attribute]:
    out = []
    for name, value in d.items():
        values = value if isinstance(value, list) else [value]
        out.append(Attribute(name, _TAG_FOR.get(name, Tag.KEYWORD), values))
    return out


def ipp_response(
    status: int = 0x0000,
    request_id: int = 1,
    job: dict[str, Any] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    printer: dict[str, Any] | None = None,
    status_msg: str | None = None,
) -> bytes:
    op: dict[str, Any] = {
        "attributes-charset": "utf-8",
        "attributes-natural-language": "en",
    }
    if status_msg:
        op["status-message"] = status_msg
    op_attrs = [
        Attribute("attributes-charset", Tag.CHARSET, ["utf-8"]),
        Attribute("attributes-natural-language", Tag.NATURAL_LANGUAGE, ["en"]),
    ]
    if status_msg:
        op_attrs.append(Attribute("status-message", Tag.TEXT, [status_msg]))
    groups: list[tuple[Tag, list[Attribute]]] = [(Tag.OPERATION_ATTRS, op_attrs)]
    if job:
        groups.append((Tag.JOB_ATTRS, _attrs(job)))
    for j in jobs or []:
        groups.append((Tag.JOB_ATTRS, _attrs(j)))
    if printer:
        groups.append((Tag.PRINTER_ATTRS, _attrs(printer)))
    return encode(IppMessage((2, 0), status, request_id, groups))
