"""Inspect source dimensions/sample profile before allocating decoder output."""

import struct


def exif_orientation(data: bytes) -> int:
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ValueError("invalid EXIF TIFF header")
    endian = "<" if data[:2] == b"II" else ">"
    if struct.unpack_from(endian + "H", data, 2)[0] != 42:
        raise ValueError("invalid EXIF TIFF marker")
    offset = struct.unpack_from(endian + "I", data, 4)[0]
    if offset + 2 > len(data):
        raise ValueError("invalid EXIF directory")
    count = struct.unpack_from(endian + "H", data, offset)[0]
    if offset + 2 + count * 12 > len(data):
        raise ValueError("truncated EXIF directory")
    for index in range(count):
        start = offset + 2 + index * 12
        tag, kind, number = struct.unpack_from(endian + "HHI", data, start)
        if tag == 274:
            if kind != 3 or number != 1:
                raise ValueError("invalid EXIF orientation field")
            return int(struct.unpack_from(endian + "H", data, start + 8)[0])
    return 1


def image_shape(data: bytes, profile: str) -> tuple[int, int, int, int]:
    if profile == "png_uint_v1":
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 33:
            raise ValueError("invalid PNG header")
        if data[12:16] != b"IHDR" or int.from_bytes(data[8:12], "big") != 13:
            raise ValueError("PNG requires initial IHDR")
        width, height, bits, color, compression, filtering, interlace = (
            struct.unpack_from(">IIBBBBB", data, 16)
        )
        if (
            color not in (0, 2, 3, 4, 6)
            or compression
            or filtering
            or interlace not in (0, 1)
        ):
            raise ValueError("unsupported PNG profile")
        if (color == 3 and bits not in (1, 2, 4, 8)) or (
            color != 3 and bits not in (8, 16)
        ):
            raise ValueError("unsupported PNG sample precision")
        channels = {0: 1, 2: 3, 3: 4, 4: 2, 6: 4}[color]
        offset = 8
        while offset + 12 <= len(data):
            length = int.from_bytes(data[offset : offset + 4], "big")
            if offset + 12 + length > len(data):
                raise ValueError("truncated PNG chunk")
            kind = data[offset + 4 : offset + 8]
            if kind == b"acTL":
                raise ValueError("animated PNG is unsupported")
            if (
                kind == b"eXIf"
                and exif_orientation(data[offset + 8 : offset + 8 + length]) != 1
            ):
                raise ValueError("unsupported image orientation")
            if kind == b"IEND":
                break
            offset += 12 + length
        if min(width, height) <= 0:
            raise ValueError("image dimensions must be positive")
        return width, height, channels, max(8, bits)
    if profile != "jpeg8_v1" or not data.startswith(b"\xff\xd8"):
        raise ValueError("invalid photographic JPEG header")
    offset = 2
    dimensions = None
    while offset < len(data):
        if data[offset] != 255:
            raise ValueError("malformed JPEG segment")
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in (0xD9, 0xDA):
            break
        if offset + 2 > len(data):
            raise ValueError("truncated JPEG segment")
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise ValueError("invalid JPEG segment length")
        payload = data[offset + 2 : offset + length]
        if (
            marker == 0xE1
            and payload.startswith(b"Exif\x00\x00")
            and exif_orientation(payload[6:]) != 1
        ):
            raise ValueError("unsupported image orientation")
        if marker == 0xE2 and payload.startswith(b"MPF\x00"):
            raise ValueError("multi-image JPEG is unsupported")
        if marker in (0xC0, 0xC2):
            if len(payload) < 6:
                raise ValueError("truncated JPEG frame header")
            bits, height, width, channels = struct.unpack_from(">BHHB", payload)
            if bits != 8 or channels not in (1, 3) or min(width, height) <= 0:
                raise ValueError("unsupported JPEG samples")
            dimensions = (width, height, channels, bits)
        elif marker in (
            0xC1,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        ):
            raise ValueError("unsupported JPEG coding profile")
        offset += length
    if dimensions is None:
        raise ValueError("JPEG has no supported frame dimensions")
    return dimensions
