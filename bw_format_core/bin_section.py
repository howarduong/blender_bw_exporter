"""BinSection (.primitives container) read/write — mirrors lib/resmgr/bin_section.cpp."""

from __future__ import annotations

import struct
from typing import Dict, List, Tuple

BIN_SECTION_MAGIC = 0x42A14E65


def _pad4(n: int) -> int:
    return (n + 3) & ~3


def read_bin_section(data: bytes) -> Dict[str, bytes]:
    """Parse BinSection file bytes into {tag: blob}."""
    if len(data) < 8:
        raise ValueError("BinSection too small")

    offset = 0
    if struct.unpack_from("<I", data, 0)[0] == BIN_SECTION_MAGIC:
        offset = 4

    index_len = struct.unpack_from("<i", data, len(data) - 4)[0]
    index_start = len(data) - 4 - index_len
    if index_start < offset:
        raise ValueError("Invalid BinSection index")

    children: Dict[str, bytes] = {}
    data_offset = offset
    pos = index_start

    while pos <= len(data) - (4 + 4):
        entry_data_len = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if entry_data_len & (1 << 31):
            entry_data_len &= ~(1 << 31)
        if pos + 16 <= len(data) - (4 + 4):
            pos += 16  # preloadLen, version, modified
        entry_name_len = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        name = data[pos : pos + entry_name_len].decode("utf-8", errors="replace")
        pos += _pad4(entry_name_len)
        blob = data[data_offset : data_offset + entry_data_len]
        children[name] = blob
        data_offset += _pad4(entry_data_len)

    return children


def write_bin_section(children: Dict[str, bytes]) -> bytes:
    """Serialize child blobs into a BinSection file."""
    ordered: List[Tuple[str, bytes]] = sorted(children.items(), key=lambda x: x[0])
    body = bytearray()
    body.extend(struct.pack("<I", BIN_SECTION_MAGIC))
    for _, blob in ordered:
        body.extend(blob)
        pad = _pad4(len(blob)) - len(blob)
        body.extend(b"\x00" * pad)

    index = bytearray()
    data_offset = 4
    for name, blob in ordered:
        name_bytes = name.encode("utf-8")
        lens = struct.pack(
            "<iiiiii",
            len(blob),
            0,
            0,
            0,
            0,
            len(name_bytes),
        )
        index.extend(lens)
        index.extend(name_bytes)
        pad = _pad4(len(name_bytes)) - len(name_bytes)
        index.extend(b"\x00" * pad)
        data_offset += _pad4(len(blob))

    index_len = len(index)
    index.extend(struct.pack("<i", index_len))
    body.extend(index)
    return bytes(body)
