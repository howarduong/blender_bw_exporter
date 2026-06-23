"""BigWorld binary file helpers (BinaryFile-compatible layout)."""

from __future__ import annotations

import struct
from typing import Callable, List, Tuple


class BinaryReader:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    @property
    def pos(self) -> int:
        return self._pos

    def remaining(self) -> int:
        return len(self._data) - self._pos

    def read(self, size: int) -> bytes:
        if self._pos + size > len(self._data):
            raise EOFError("Unexpected end of binary data")
        chunk = self._data[self._pos : self._pos + size]
        self._pos += size
        return chunk

    def read_f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def read_i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def read_u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def read_string(self) -> str:
        length = self.read_i32()
        if length <= 0:
            return ""
        return self.read(length).decode("utf-8", errors="replace")

    def read_pair_f_vec3(self) -> Tuple[float, Tuple[float, float, float]]:
        t = self.read_f32()
        x, y, z = struct.unpack("<3f", self.read(12))
        return t, (x, y, z)

    def read_pair_f_quat(self) -> Tuple[float, Tuple[float, float, float, float]]:
        t = self.read_f32()
        x, y, z, w = struct.unpack("<4f", self.read(16))
        return t, (x, y, z, w)

    def read_sequence(self, reader: Callable[[], object]) -> List:
        count = self.read_u32()
        return [reader() for _ in range(count)]


class BinaryWriter:
    def __init__(self):
        self._buf = bytearray()

    def to_bytes(self) -> bytes:
        return bytes(self._buf)

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    def write_f32(self, value: float) -> None:
        self.write(struct.pack("<f", value))

    def write_i32(self, value: int) -> None:
        self.write(struct.pack("<i", value))

    def write_u32(self, value: int) -> None:
        self.write(struct.pack("<I", value))

    def write_string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.write_i32(len(encoded))
        if encoded:
            self.write(encoded)

    def write_pair_f_vec3(self, time: float, vec: Tuple[float, float, float]) -> None:
        self.write_f32(time)
        self.write(struct.pack("<3f", *vec))

    def write_pair_f_quat(
        self, time: float, quat: Tuple[float, float, float, float]
    ) -> None:
        self.write_f32(time)
        self.write(struct.pack("<4f", *quat))

    def write_sequence(self, items: List, writer: Callable[[object], None]) -> None:
        self.write_u32(len(items))
        for item in items:
            writer(item)
