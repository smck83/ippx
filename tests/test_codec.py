"""Codec round-trip and edge case tests."""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone

import pytest

from ippx import Attribute, IppMessage, Resolution, Tag, decode, encode
from ippx.exceptions import IppDecodeError


def roundtrip(msg: IppMessage) -> IppMessage:
    return decode(encode(msg))


def simple_message(attrs: list[Attribute], data: bytes = b"") -> IppMessage:
    return IppMessage((2, 0), 0x0002, 42, [(Tag.OPERATION_ATTRS, attrs)], data)


def test_header_roundtrip() -> None:
    msg = simple_message([Attribute("attributes-charset", Tag.CHARSET, ["utf-8"])])
    out = roundtrip(msg)
    assert out.version == (2, 0)
    assert out.code == 0x0002
    assert out.request_id == 42


@pytest.mark.parametrize(
    ("tag", "value"),
    [
        (Tag.INTEGER, 12345),
        (Tag.INTEGER, -1),
        (Tag.ENUM, 9),
        (Tag.BOOLEAN, True),
        (Tag.BOOLEAN, False),
        (Tag.KEYWORD, "one-sided"),
        (Tag.NAME, "Invoice 123"),
        (Tag.TEXT, "hello world"),
        (Tag.URI, "ipps://printer.local:631/ipp/print"),
        (Tag.MIME_TYPE, "application/pdf"),
        (Tag.OCTET_STRING, b"\x00\x01\xff"),
        (Tag.RESOLUTION, Resolution(600, 600, 3)),
        (Tag.RANGE, (1, 100)),
        (Tag.NO_VALUE, None),
    ],
)
def test_value_roundtrip(tag: Tag, value: object) -> None:
    msg = simple_message([Attribute("x", tag, [value])])
    out = roundtrip(msg)
    assert out.groups[0][1][0].values == [value]
    assert out.groups[0][1][0].tag == tag


def test_datetime_roundtrip() -> None:
    dt = datetime(2026, 6, 13, 9, 30, 15, 500_000, timezone(timedelta(hours=10)))
    msg = simple_message([Attribute("d", Tag.DATETIME, [dt])])
    assert roundtrip(msg).groups[0][1][0].values == [dt]


def test_multi_value_roundtrip() -> None:
    msg = simple_message([Attribute("requested-attributes", Tag.KEYWORD, ["job-state", "job-id"])])
    out = roundtrip(msg)
    assert out.groups[0][1][0].values == ["job-state", "job-id"]


def test_document_data_preserved() -> None:
    payload = b"%PDF-1.7 fake document bytes"
    msg = simple_message([Attribute("attributes-charset", Tag.CHARSET, ["utf-8"])], payload)
    assert roundtrip(msg).data == payload


def test_multiple_groups() -> None:
    msg = IppMessage(
        (2, 0),
        0x0000,
        1,
        [
            (Tag.OPERATION_ATTRS, [Attribute("attributes-charset", Tag.CHARSET, ["utf-8"])]),
            (Tag.JOB_ATTRS, [Attribute("job-id", Tag.INTEGER, [7])]),
            (Tag.JOB_ATTRS, [Attribute("job-id", Tag.INTEGER, [8])]),
        ],
    )
    out = roundtrip(msg)
    assert [g[0] for g in out.groups] == [Tag.OPERATION_ATTRS, Tag.JOB_ATTRS, Tag.JOB_ATTRS]
    assert out.groups[2][1][0].values == [8]


def _attr_bytes(tag: int, name: bytes, value: bytes) -> bytes:
    return (
        bytes([tag]) + struct.pack(">H", len(name)) + name + struct.pack(">H", len(value)) + value
    )


def _message(group_tag: Tag, body: bytes) -> bytes:
    header = bytes([2, 0]) + struct.pack(">HI", 0x0000, 1)
    return header + bytes([group_tag]) + body + bytes([Tag.END])


def test_decode_collection() -> None:
    # hand-built media-col = { media-size = { x-dimension=21000, y-dimension=29700 } }
    body = b""
    body += _attr_bytes(Tag.BEG_COLLECTION, b"media-col", b"")
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"media-size")
    body += _attr_bytes(Tag.BEG_COLLECTION, b"", b"")
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"x-dimension")
    body += _attr_bytes(Tag.INTEGER, b"", struct.pack(">i", 21000))
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"y-dimension")
    body += _attr_bytes(Tag.INTEGER, b"", struct.pack(">i", 29700))
    body += _attr_bytes(Tag.END_COLLECTION, b"", b"")
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"media-source")
    body += _attr_bytes(Tag.KEYWORD, b"", b"tray-1")
    body += _attr_bytes(Tag.END_COLLECTION, b"", b"")

    msg = decode(_message(Tag.PRINTER_ATTRS, body))
    attr = msg.groups[0][1][0]
    assert attr.name == "media-col"
    assert attr.values[0] == {
        "media-size": {"x-dimension": 21000, "y-dimension": 29700},
        "media-source": "tray-1",
    }


def test_decode_set_of_collections() -> None:
    body = b""
    body += _attr_bytes(Tag.BEG_COLLECTION, b"sizes", b"")
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"x")
    body += _attr_bytes(Tag.INTEGER, b"", struct.pack(">i", 1))
    body += _attr_bytes(Tag.END_COLLECTION, b"", b"")
    body += _attr_bytes(Tag.BEG_COLLECTION, b"", b"")  # additional value
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"x")
    body += _attr_bytes(Tag.INTEGER, b"", struct.pack(">i", 2))
    body += _attr_bytes(Tag.END_COLLECTION, b"", b"")
    attr = decode(_message(Tag.PRINTER_ATTRS, body)).groups[0][1][0]
    assert attr.values == [{"x": 1}, {"x": 2}]


def test_text_with_language() -> None:
    value = struct.pack(">H", 2) + b"en" + struct.pack(">H", 5) + b"hello"
    body = _attr_bytes(Tag.TEXT_WITH_LANG, b"status-message", value)
    assert decode(_message(Tag.OPERATION_ATTRS, body)).groups[0][1][0].values == ["hello"]


def test_truncated_message_raises() -> None:
    with pytest.raises(IppDecodeError):
        decode(b"\x02\x00\x00")


def test_missing_end_tag_raises() -> None:
    raw = bytes([2, 0]) + struct.pack(">HI", 0x0000, 1) + bytes([Tag.OPERATION_ATTRS])
    with pytest.raises(IppDecodeError):
        decode(raw)


def test_collection_encoding_not_supported() -> None:
    msg = simple_message([Attribute("media-col", Tag.BEG_COLLECTION, [{"a": 1}])])
    with pytest.raises(NotImplementedError):
        encode(msg)


def test_malformed_integer_raises_decode_error() -> None:
    body = _attr_bytes(Tag.INTEGER, b"x", b"\x00\x01")  # 2 bytes, needs 4
    with pytest.raises(IppDecodeError, match="malformed INTEGER"):
        decode(_message(Tag.OPERATION_ATTRS, body))


def test_truncated_text_with_language_raises_decode_error() -> None:
    body = _attr_bytes(Tag.TEXT_WITH_LANG, b"m", b"\x00")
    with pytest.raises(IppDecodeError, match="malformed TEXT_WITH_LANG"):
        decode(_message(Tag.OPERATION_ATTRS, body))


def test_reserved_delimiter_raises_decode_error() -> None:
    raw = bytes([2, 0]) + struct.pack(">HI", 0x0000, 1) + bytes([0x06, Tag.END])
    with pytest.raises(IppDecodeError, match="reserved delimiter"):
        decode(raw)


def test_empty_values_list_rejected_on_encode() -> None:
    msg = simple_message([Attribute("k", Tag.KEYWORD, [])])
    with pytest.raises(ValueError, match="no values"):
        encode(msg)


def test_unknown_tag_inside_collection_kept_as_raw_bytes() -> None:
    body = b""
    body += _attr_bytes(Tag.BEG_COLLECTION, b"col", b"")
    body += _attr_bytes(Tag.MEMBER_ATTR_NAME, b"", b"m")
    body += _attr_bytes(0x7F, b"", b"zz")  # unknown value tag
    body += _attr_bytes(Tag.END_COLLECTION, b"", b"")
    attr = decode(_message(Tag.PRINTER_ATTRS, body)).groups[0][1][0]
    assert attr.values == [{"m": b"zz"}]


def test_unknown_tag_at_top_level_kept_as_octet_string() -> None:
    body = _attr_bytes(0x7F, b"vendor-thing", b"\x01\x02")
    attr = decode(_message(Tag.OPERATION_ATTRS, body)).groups[0][1][0]
    assert attr.tag == Tag.OCTET_STRING
    assert attr.values == [b"\x01\x02"]
