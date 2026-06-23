"""Vertex format constants aligned with lib/moo/vertex_formats.hpp."""

from __future__ import annotations

VERTEX_FORMAT_XYZNUV = "xyznuv"
VERTEX_FORMAT_XYZNUVTB = "xyznuvtb"
VERTEX_FORMAT_XYZNUVIIIWW = "xyznuviiiww"
VERTEX_FORMAT_XYZNUVIIIWWTB = "xyznuviiiwwtb"

INDEX_FORMAT_LIST = "list"
INDEX_FORMAT_LIST32 = "list32"

# CPU-side VertexXYZNUV: Vector3 + Vector3 + Vector2
VERTEX_XYZNUV_SIZE = 32
# Packed normal + tangent + binormal (uint32 each); same stride as xyznuv in disk layout
VERTEX_XYZNUVTB_SIZE = 32

# Skinned: adds 3x uint8 index + 3x uint8 weight (packed)
VERTEX_XYZNUVIIIWW_SIZE = 32 + 6

SUPPORTED_READ_FORMATS = {
    VERTEX_FORMAT_XYZNUV,
    VERTEX_FORMAT_XYZNUVTB,
    VERTEX_FORMAT_XYZNUVIIIWW,
    VERTEX_FORMAT_XYZNUVIIIWWTB,
}

SUPPORTED_WRITE_FORMATS = {
    VERTEX_FORMAT_XYZNUV,
    VERTEX_FORMAT_XYZNUVTB,
    VERTEX_FORMAT_XYZNUVIIIWW,
}

MAX_BONE_INFLUENCES = 3
