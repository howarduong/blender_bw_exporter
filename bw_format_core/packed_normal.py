"""Pack/unpack normals for xyznuvtb (matches visualexporter packNormal)."""

from __future__ import annotations

import math
import struct
from typing import Tuple


def pack_normal(x: float, y: float, z: float, legacy: bool = False) -> int:
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / length, y / length, z / length
    x = max(-1.0, min(1.0, x))
    y = max(-1.0, min(1.0, y))
    z = max(-1.0, min(1.0, z))
    if legacy:
        return (
            ((int(-y * 511.0) & 0x3FF) << 22)
            | ((int(z * 1023.0) & 0x7FF) << 11)
            | ((int(-x * 1023.0) & 0x7FF) << 0)
        )
    return (
        ((int(y * 511.0) & 0x3FF) << 22)
        | ((int(z * 1023.0) & 0x7FF) << 11)
        | ((int(x * 1023.0) & 0x7FF) << 0)
    )


def unpack_normal(packed: int, legacy: bool = False) -> Tuple[float, float, float]:
    y_bits = (packed >> 22) & 0x3FF
    z_bits = (packed >> 11) & 0x7FF
    x_bits = packed & 0x7FF
    if legacy:
        y = -y_bits / 511.0
        z = z_bits / 1023.0
        x = -x_bits / 1023.0
    else:
        y = y_bits / 511.0
        z = z_bits / 1023.0
        x = x_bits / 1023.0
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return x / length, y / length, z / length


def write_xyznuvtb_vertex(body: bytearray, pos, uv, normal, tangent, binormal) -> None:
    body.extend(
        struct.pack(
            "<3fI2fII",
            *pos,
            pack_normal(*normal),
            *uv,
            pack_normal(*tangent),
            pack_normal(*binormal),
        )
    )
