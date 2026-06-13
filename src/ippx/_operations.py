"""Request builders and response parsers. Shared by sync and async clients."""

from __future__ import annotations

import contextlib
from typing import Any

from ._codec import Attribute, IppMessage, Tag
from ._models import Job, JobState, Operation, Printer, PrinterState

DEFAULT_VERSION: tuple[int, int] = (2, 0)

# tag mapping for common Job Template attributes so callers can pass plain dicts
JOB_TEMPLATE_TAGS: dict[str, Tag] = {
    "copies": Tag.INTEGER,
    "job-priority": Tag.INTEGER,
    "number-up": Tag.INTEGER,
    "orientation-requested": Tag.ENUM,
    "print-quality": Tag.ENUM,
    "finishings": Tag.ENUM,
    "sides": Tag.KEYWORD,
    "media": Tag.KEYWORD,
    "media-source": Tag.KEYWORD,
    "output-bin": Tag.KEYWORD,
    "print-color-mode": Tag.KEYWORD,
    "print-scaling": Tag.KEYWORD,
    "multiple-document-handling": Tag.KEYWORD,
    "printer-resolution": Tag.RESOLUTION,
    "job-hold-until": Tag.KEYWORD,
}


def _infer_tag(name: str, value: Any) -> Tag:
    if name in JOB_TEMPLATE_TAGS:
        return JOB_TEMPLATE_TAGS[name]
    if isinstance(value, bool):
        return Tag.BOOLEAN
    if isinstance(value, int):
        return Tag.INTEGER
    if isinstance(value, bytes):
        return Tag.OCTET_STRING
    return Tag.KEYWORD


def build_job_attributes(
    job_attributes: dict[str, Any] | list[Attribute] | None,
) -> list[Attribute]:
    if not job_attributes:
        return []
    if isinstance(job_attributes, list):
        return job_attributes
    attrs: list[Attribute] = []
    for name, value in job_attributes.items():
        values = value if isinstance(value, list) else [value]
        attrs.append(Attribute(name, _infer_tag(name, values[0]), values))
    return attrs


def operation_attrs(
    printer_uri: str,
    requesting_user_name: str | None,
    extra: list[Attribute] | None = None,
) -> list[Attribute]:
    """Build the operation attributes group. Order matters: charset and
    natural-language MUST be first and second (RFC 8011 section 4.1.4)."""
    attrs = [
        Attribute("attributes-charset", Tag.CHARSET, ["utf-8"]),
        Attribute("attributes-natural-language", Tag.NATURAL_LANGUAGE, ["en"]),
        Attribute("printer-uri", Tag.URI, [printer_uri]),
    ]
    if requesting_user_name:
        attrs.append(Attribute("requesting-user-name", Tag.NAME, [requesting_user_name]))
    if extra:
        attrs.extend(extra)
    return attrs


def print_job_request(
    *,
    printer_uri: str,
    request_id: int,
    document: bytes,
    document_format: str,
    job_name: str | None,
    requesting_user_name: str | None,
    job_attributes: dict[str, Any] | list[Attribute] | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra: list[Attribute] = []
    if job_name:
        extra.append(Attribute("job-name", Tag.NAME, [job_name]))
    extra.append(Attribute("document-format", Tag.MIME_TYPE, [document_format]))
    groups: list[tuple[Tag, list[Attribute]]] = [
        (Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))
    ]
    job_attrs = build_job_attributes(job_attributes)
    if job_attrs:
        groups.append((Tag.JOB_ATTRS, job_attrs))
    return IppMessage(version, Operation.PRINT_JOB, request_id, groups, document)


def validate_job_request(
    *,
    printer_uri: str,
    request_id: int,
    document_format: str,
    requesting_user_name: str | None,
    job_attributes: dict[str, Any] | list[Attribute] | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra = [Attribute("document-format", Tag.MIME_TYPE, [document_format])]
    groups: list[tuple[Tag, list[Attribute]]] = [
        (Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))
    ]
    job_attrs = build_job_attributes(job_attributes)
    if job_attrs:
        groups.append((Tag.JOB_ATTRS, job_attrs))
    return IppMessage(version, Operation.VALIDATE_JOB, request_id, groups)


def get_printer_attributes_request(
    *,
    printer_uri: str,
    request_id: int,
    requesting_user_name: str | None,
    requested_attributes: list[str] | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra: list[Attribute] = []
    if requested_attributes:
        extra.append(Attribute("requested-attributes", Tag.KEYWORD, list(requested_attributes)))
    return IppMessage(
        version,
        Operation.GET_PRINTER_ATTRIBUTES,
        request_id,
        [(Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))],
    )


def get_job_attributes_request(
    *,
    printer_uri: str,
    request_id: int,
    job_id: int,
    requesting_user_name: str | None,
    requested_attributes: list[str] | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra = [Attribute("job-id", Tag.INTEGER, [job_id])]
    if requested_attributes:
        extra.append(Attribute("requested-attributes", Tag.KEYWORD, list(requested_attributes)))
    return IppMessage(
        version,
        Operation.GET_JOB_ATTRIBUTES,
        request_id,
        [(Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))],
    )


def cancel_job_request(
    *,
    printer_uri: str,
    request_id: int,
    job_id: int,
    requesting_user_name: str | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra = [Attribute("job-id", Tag.INTEGER, [job_id])]
    return IppMessage(
        version,
        Operation.CANCEL_JOB,
        request_id,
        [(Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))],
    )


def get_jobs_request(
    *,
    printer_uri: str,
    request_id: int,
    requesting_user_name: str | None,
    which_jobs: str,
    my_jobs: bool,
    limit: int | None,
    requested_attributes: list[str] | None,
    version: tuple[int, int] = DEFAULT_VERSION,
) -> IppMessage:
    extra = [Attribute("which-jobs", Tag.KEYWORD, [which_jobs])]
    if my_jobs:
        extra.append(Attribute("my-jobs", Tag.BOOLEAN, [True]))
    if limit is not None:
        extra.append(Attribute("limit", Tag.INTEGER, [limit]))
    if requested_attributes:
        extra.append(Attribute("requested-attributes", Tag.KEYWORD, list(requested_attributes)))
    return IppMessage(
        version,
        Operation.GET_JOBS,
        request_id,
        [(Tag.OPERATION_ATTRS, operation_attrs(printer_uri, requesting_user_name, extra))],
    )


# ---------------------------------------------------------------------------
# response parsing


def attrs_to_dict(attrs: list[Attribute]) -> dict[str, Any]:
    """Collapse a group's attribute list into a dict. Single values become
    scalars, multi-values stay as lists."""
    out: dict[str, Any] = {}
    for attr in attrs:
        out[attr.name] = attr.values[0] if len(attr.values) == 1 else attr.values
    return out


def first_group(msg: IppMessage, tag: Tag) -> dict[str, Any]:
    for group_tag, attrs in msg.groups:
        if group_tag == tag:
            return attrs_to_dict(attrs)
    return {}


def all_groups(msg: IppMessage, tag: Tag) -> list[dict[str, Any]]:
    return [attrs_to_dict(attrs) for group_tag, attrs in msg.groups if group_tag == tag]


def status_message(msg: IppMessage) -> str | None:
    op = first_group(msg, Tag.OPERATION_ATTRS)
    value = op.get("status-message")
    return value if isinstance(value, str) else None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_job(attrs: dict[str, Any]) -> Job:
    state: JobState | int | None = attrs.get("job-state")
    if isinstance(state, int):
        with contextlib.suppress(ValueError):
            state = JobState(state)
    return Job(
        job_id=int(attrs.get("job-id", 0)),
        state=state,
        state_reasons=[str(r) for r in _as_list(attrs.get("job-state-reasons"))],
        name=attrs.get("job-name"),
        uri=attrs.get("job-uri"),
        attributes=attrs,
    )


def parse_printer(attrs: dict[str, Any]) -> Printer:
    state: PrinterState | int | None = attrs.get("printer-state")
    if isinstance(state, int):
        with contextlib.suppress(ValueError):
            state = PrinterState(state)
    ops: list[Operation | int] = []
    for op in _as_list(attrs.get("operations-supported")):
        if isinstance(op, int):
            try:
                ops.append(Operation(op))
            except ValueError:
                ops.append(op)
    return Printer(
        name=attrs.get("printer-name"),
        make_and_model=attrs.get("printer-make-and-model"),
        state=state,
        state_reasons=[str(r) for r in _as_list(attrs.get("printer-state-reasons"))],
        state_message=attrs.get("printer-state-message"),
        is_accepting_jobs=attrs.get("printer-is-accepting-jobs"),
        document_formats=[str(f) for f in _as_list(attrs.get("document-format-supported"))],
        operations_supported=ops,
        uri_supported=[str(u) for u in _as_list(attrs.get("printer-uri-supported"))],
        attributes=attrs,
    )
