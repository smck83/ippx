"""RFC 8010 IPP binary encoding and decoding. Pure functions, no I/O."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Any

from .exceptions import IppDecodeError


class Tag(IntEnum):
    """IPP delimiter and value tags (RFC 8010 section 3.5)."""

    # delimiter tags
    OPERATION_ATTRS = 0x01
    JOB_ATTRS = 0x02
    END = 0x03
    PRINTER_ATTRS = 0x04
    UNSUPPORTED_ATTRS = 0x05
    # out-of-band
    UNSUPPORTED = 0x10
    UNKNOWN = 0x12
    NO_VALUE = 0x13
    # integer types
    INTEGER = 0x21
    BOOLEAN = 0x22
    ENUM = 0x23
    # octet-string types
    OCTET_STRING = 0x30
    DATETIME = 0x31
    RESOLUTION = 0x32
    RANGE = 0x33
    BEG_COLLECTION = 0x34
    TEXT_WITH_LANG = 0x35
    NAME_WITH_LANG = 0x36
    END_COLLECTION = 0x37
    # character-string types
    TEXT = 0x41
    NAME = 0x42
    KEYWORD = 0x44
    URI = 0x45
    URI_SCHEME = 0x46
    CHARSET = 0x47
    NATURAL_LANGUAGE = 0x48
    MIME_TYPE = 0x49
    MEMBER_ATTR_NAME = 0x4A


_OUT_OF_BAND = frozenset({Tag.UNSUPPORTED, Tag.UNKNOWN, Tag.NO_VALUE})
_DELIMITER_MAX = 0x0F


@dataclass(frozen=True)
class Resolution:
    x: int
    y: int
    units: int  # 3 = dots per inch, 4 = dots per cm

    def __str__(self) -> str:
        unit = {3: "dpi", 4: "dpcm"}.get(self.units, f"units={self.units}")
        return f"{self.x}x{self.y} {unit}"


@dataclass
class Attribute:
    """A single IPP attribute. ``values`` holds one or more Python values."""

    name: str
    tag: Tag
    values: list[Any]

    @property
    def value(self) -> Any:
        return self.values[0] if self.values else None


@dataclass
class IppMessage:
    """An IPP request or response.

    ``code`` is the operation-id in a request or the status-code in a response.
    ``data`` is the document payload (requests) or trailing data (responses).
    """

    version: tuple[int, int]
    code: int
    request_id: int
    groups: list[tuple[Tag, list[Attribute]]] = field(default_factory=list)
    data: bytes = b""


def encode(msg: IppMessage) -> bytes:
    out = bytearray()
    out += bytes((msg.version[0], msg.version[1]))
    out += struct.pack(">HI", msg.code, msg.request_id)
    for group_tag, attrs in msg.groups:
        out.append(group_tag)
        for attr in attrs:
            if not attr.values:
                raise ValueError(
                    f"attribute {attr.name!r} has no values; use [None] for out-of-band tags"
                )
            first = True
            for value in attr.values:
                out.append(attr.tag)
                name_b = attr.name.encode("utf-8") if first else b""
                out += struct.pack(">H", len(name_b)) + name_b
                value_b = _encode_value(attr.tag, value)
                out += struct.pack(">H", len(value_b)) + value_b
                first = False
    out.append(Tag.END)
    out += msg.data
    return bytes(out)


def _encode_value(tag: Tag, value: Any) -> bytes:
    if tag in _OUT_OF_BAND:
        return b""
    if tag in (Tag.INTEGER, Tag.ENUM):
        return struct.pack(">i", int(value))
    if tag == Tag.BOOLEAN:
        return b"\x01" if value else b"\x00"
    if tag == Tag.DATETIME:
        return _encode_datetime(value)
    if tag == Tag.RESOLUTION:
        res = value if isinstance(value, Resolution) else Resolution(*value)
        return struct.pack(">iib", res.x, res.y, res.units)
    if tag == Tag.RANGE:
        lo, hi = value
        return struct.pack(">ii", lo, hi)
    if tag == Tag.BEG_COLLECTION:
        raise NotImplementedError("encoding IPP collections is not supported yet")
    if tag == Tag.OCTET_STRING:
        return bytes(value)
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _encode_datetime(value: datetime) -> bytes:
    offset = value.utcoffset() or timedelta(0)
    total = int(offset.total_seconds())
    sign = b"+" if total >= 0 else b"-"
    total = abs(total)
    return struct.pack(
        ">H6Bc2B",
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond // 100_000,
        sign,
        total // 3600,
        (total % 3600) // 60,
    )


def decode(data: bytes) -> IppMessage:
    if len(data) < 9:
        raise IppDecodeError(f"IPP message too short: {len(data)} bytes")
    version = (data[0], data[1])
    code, request_id = struct.unpack(">HI", data[2:8])
    pos = 8

    groups: list[tuple[Tag, list[Attribute]]] = []
    current_tag: Tag | None = None
    current: list[Attribute] = []
    # collection parsing stack: each frame is [values_dict, member_name, attr_name]
    frames: list[list[Any]] = []
    ended = False

    def flush_group() -> None:
        nonlocal current, current_tag
        if current_tag is not None:
            groups.append((current_tag, current))
        current = []

    def deliver(name: str, tag: Tag, value: Any) -> None:
        if name:
            current.append(Attribute(name, tag, [value]))
        elif current:
            current[-1].values.append(value)
        else:
            raise IppDecodeError("additional value with no preceding attribute")

    while pos < len(data):
        tag_byte = data[pos]
        pos += 1
        if tag_byte <= _DELIMITER_MAX:
            if frames:
                raise IppDecodeError("delimiter inside collection")
            if tag_byte == Tag.END:
                ended = True
                break
            flush_group()
            try:
                current_tag = Tag(tag_byte)
            except ValueError as exc:
                raise IppDecodeError(f"reserved delimiter tag 0x{tag_byte:02X}") from exc
            continue

        if pos + 2 > len(data):
            raise IppDecodeError("truncated attribute name length")
        (name_len,) = struct.unpack(">H", data[pos : pos + 2])
        pos += 2
        name = data[pos : pos + name_len].decode("utf-8", "replace")
        pos += name_len
        if pos + 2 > len(data):
            raise IppDecodeError("truncated attribute value length")
        (value_len,) = struct.unpack(">H", data[pos : pos + 2])
        pos += 2
        raw = data[pos : pos + value_len]
        if len(raw) != value_len:
            raise IppDecodeError("truncated attribute value")
        pos += value_len

        try:
            tag = Tag(tag_byte)
        except ValueError:
            # unknown value tag: keep raw bytes under the closest semantics
            if frames:
                _frame_append(frames[-1], bytes(raw))
            else:
                deliver(name, Tag.OCTET_STRING, bytes(raw))
            continue

        if tag == Tag.BEG_COLLECTION:
            frames.append([{}, None, name])
            continue
        if tag == Tag.END_COLLECTION:
            if not frames:
                raise IppDecodeError("endCollection without begCollection")
            values_dict, _, attr_name = frames.pop()
            collapsed = {k: (v[0] if len(v) == 1 else v) for k, v in values_dict.items()}
            if frames:
                _frame_append(frames[-1], collapsed)
            else:
                deliver(attr_name, Tag.BEG_COLLECTION, collapsed)
            continue

        try:
            value = _decode_value(tag, raw)
        except (struct.error, ValueError, IndexError) as exc:
            raise IppDecodeError(
                f"malformed {tag.name} value for {name!r} ({len(raw)} bytes)"
            ) from exc
        if frames:
            if tag == Tag.MEMBER_ATTR_NAME:
                frame = frames[-1]
                frame[1] = value
                frame[0].setdefault(value, [])
            else:
                _frame_append(frames[-1], value)
        else:
            deliver(name, tag, value)

    if frames:
        raise IppDecodeError("unterminated collection")
    if not ended:
        raise IppDecodeError("missing end-of-attributes tag")
    flush_group()
    return IppMessage(version, code, request_id, groups, bytes(data[pos:]))


def _frame_append(frame: list[Any], value: Any) -> None:
    member = frame[1]
    if member is None:
        raise IppDecodeError("collection member value before memberAttrName")
    frame[0][member].append(value)


def _decode_value(tag: Tag, raw: bytes) -> Any:
    if tag in _OUT_OF_BAND:
        return None
    if tag in (Tag.INTEGER, Tag.ENUM):
        return struct.unpack(">i", raw)[0]
    if tag == Tag.BOOLEAN:
        return raw != b"\x00"
    if tag == Tag.DATETIME:
        return _decode_datetime(raw)
    if tag == Tag.RESOLUTION:
        x, y, units = struct.unpack(">iib", raw)
        return Resolution(x, y, units)
    if tag == Tag.RANGE:
        lo, hi = struct.unpack(">ii", raw)
        return (lo, hi)
    if tag in (Tag.TEXT_WITH_LANG, Tag.NAME_WITH_LANG):
        (lang_len,) = struct.unpack(">H", raw[:2])
        (text_len,) = struct.unpack(">H", raw[2 + lang_len : 4 + lang_len])
        return raw[4 + lang_len : 4 + lang_len + text_len].decode("utf-8", "replace")
    if tag == Tag.OCTET_STRING:
        return bytes(raw)
    if tag >= Tag.TEXT:
        return raw.decode("utf-8", "replace")
    return bytes(raw)


def _decode_datetime(raw: bytes) -> Any:
    try:
        year, month, day, hour, minute, second, deci, sign, tzh, tzm = struct.unpack(">H6Bc2B", raw)
        delta = timedelta(hours=tzh, minutes=tzm)
        if sign == b"-":
            delta = -delta
        return datetime(year, month, day, hour, minute, second, deci * 100_000, timezone(delta))
    except (struct.error, ValueError):
        return bytes(raw)
