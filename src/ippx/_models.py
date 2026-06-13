"""Enums and result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Operation(IntEnum):
    """IPP operation-ids from the IANA IPP registry (operations-supported).

    Names and codes track the registry maintained by the PWG IPP workgroup;
    ``(deprecated)`` markers from the registry are dropped from the member
    names. ippx implements the RFC 8011 required set; the rest are here so a
    printer's ``operations-supported`` list decodes to readable names rather
    than bare integers.
    """

    PRINT_JOB = 0x0002
    PRINT_URI = 0x0003  # deprecated
    VALIDATE_JOB = 0x0004
    CREATE_JOB = 0x0005
    SEND_DOCUMENT = 0x0006
    SEND_URI = 0x0007  # deprecated
    CANCEL_JOB = 0x0008
    GET_JOB_ATTRIBUTES = 0x0009
    GET_JOBS = 0x000A
    GET_PRINTER_ATTRIBUTES = 0x000B
    HOLD_JOB = 0x000C
    RELEASE_JOB = 0x000D
    RESTART_JOB = 0x000E  # deprecated
    PAUSE_PRINTER = 0x0010
    RESUME_PRINTER = 0x0011
    PURGE_JOBS = 0x0012  # deprecated
    SET_PRINTER_ATTRIBUTES = 0x0013
    SET_JOB_ATTRIBUTES = 0x0014
    GET_PRINTER_SUPPORTED_VALUES = 0x0015
    CREATE_PRINTER_SUBSCRIPTIONS = 0x0016
    CREATE_JOB_SUBSCRIPTIONS = 0x0017
    GET_SUBSCRIPTION_ATTRIBUTES = 0x0018
    GET_SUBSCRIPTIONS = 0x0019
    RENEW_SUBSCRIPTION = 0x001A
    CANCEL_SUBSCRIPTION = 0x001B
    GET_NOTIFICATIONS = 0x001C
    GET_RESOURCE_ATTRIBUTES = 0x001E
    GET_RESOURCES = 0x0020
    ENABLE_PRINTER = 0x0022
    DISABLE_PRINTER = 0x0023
    PAUSE_PRINTER_AFTER_CURRENT_JOB = 0x0024
    HOLD_NEW_JOBS = 0x0025
    RELEASE_HELD_NEW_JOBS = 0x0026
    DEACTIVATE_PRINTER = 0x0027
    ACTIVATE_PRINTER = 0x0028
    RESTART_PRINTER = 0x0029
    SHUTDOWN_PRINTER = 0x002A
    STARTUP_PRINTER = 0x002B
    REPROCESS_JOB = 0x002C  # deprecated
    CANCEL_CURRENT_JOB = 0x002D
    SUSPEND_CURRENT_JOB = 0x002E
    RESUME_JOB = 0x002F
    PROMOTE_JOB = 0x0030
    SCHEDULE_JOB_AFTER = 0x0031
    CANCEL_DOCUMENT = 0x0033
    GET_DOCUMENT_ATTRIBUTES = 0x0034
    GET_DOCUMENTS = 0x0035
    DELETE_DOCUMENT = 0x0036  # obsolete
    SET_DOCUMENT_ATTRIBUTES = 0x0037
    CANCEL_JOBS = 0x0038
    CANCEL_MY_JOBS = 0x0039
    RESUBMIT_JOB = 0x003A
    CLOSE_JOB = 0x003B
    IDENTIFY_PRINTER = 0x003C
    VALIDATE_DOCUMENT = 0x003D
    ADD_DOCUMENT_IMAGES = 0x003E
    ACKNOWLEDGE_DOCUMENT = 0x003F
    ACKNOWLEDGE_IDENTIFY_PRINTER = 0x0040
    ACKNOWLEDGE_JOB = 0x0041
    FETCH_DOCUMENT = 0x0042
    FETCH_JOB = 0x0043
    GET_OUTPUT_DEVICE_ATTRIBUTES = 0x0044
    UPDATE_ACTIVE_JOBS = 0x0045
    DEREGISTER_OUTPUT_DEVICE = 0x0046


class JobState(IntEnum):
    PENDING = 3
    PENDING_HELD = 4
    PROCESSING = 5
    PROCESSING_STOPPED = 6
    CANCELED = 7
    ABORTED = 8
    COMPLETED = 9

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset({JobState.CANCELED, JobState.ABORTED, JobState.COMPLETED})


class PrinterState(IntEnum):
    IDLE = 3
    PROCESSING = 4
    STOPPED = 5


@dataclass
class Job:
    """A print job as reported by the printer."""

    job_id: int
    state: JobState | int | None = None
    state_reasons: list[str] = field(default_factory=list)
    name: str | None = None
    uri: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return isinstance(self.state, JobState) and self.state.is_terminal


@dataclass
class Printer:
    """Printer description and status attributes."""

    name: str | None = None
    make_and_model: str | None = None
    state: PrinterState | int | None = None
    state_reasons: list[str] = field(default_factory=list)
    state_message: str | None = None
    is_accepting_jobs: bool | None = None
    document_formats: list[str] = field(default_factory=list)
    operations_supported: list[Operation | int] = field(default_factory=list)
    uri_supported: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def supports_operation(self, op: Operation) -> bool:
        return op in self.operations_supported

    def supports_format(self, mime_type: str) -> bool:
        return mime_type in self.document_formats
