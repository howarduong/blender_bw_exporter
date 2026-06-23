"""BigWorld .primitives BinSection geometry I/O."""

from __future__ import annotations

import struct
from typing import Dict, List, Tuple

from .bin_section import read_bin_section, write_bin_section
from .ir import MeshChunk, PrimitiveGroup
from .packed_normal import pack_normal, unpack_normal, write_xyznuvtb_vertex
from .vertex_formats import (
    INDEX_FORMAT_LIST,
    INDEX_FORMAT_LIST32,
    MAX_BONE_INFLUENCES,
    VERTEX_FORMAT_XYZNUV,
    VERTEX_FORMAT_XYZNUVTB,
    VERTEX_FORMAT_XYZNUVIIIWW,
    VERTEX_FORMAT_XYZNUVIIIWWTB,
)

INDEX_HEADER_SIZE = 64 + 4 + 4
VERTEX_HEADER_SIZE = 64 + 4

BONE_INDEX_SCALE = 3


def _disk_bone_indices(bind: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return tuple(min(255, idx * BONE_INDEX_SCALE) for idx in bind)


def _ir_bone_indices(bind: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return tuple(idx // BONE_INDEX_SCALE for idx in bind)


def _parse_index_header(data: bytes):
    fmt = data[:64].split(b"\x00", 1)[0].decode("ascii", errors="replace")
    n_indices, n_groups = struct.unpack_from("<ii", data, 64)
    return fmt, n_indices, n_groups


def _parse_vertex_header(data: bytes):
    fmt = data[:64].split(b"\x00", 1)[0].decode("ascii", errors="replace")
    (n_vertices,) = struct.unpack_from("<i", data, 64)
    return fmt, n_vertices


def _read_indices(data: bytes, mesh: MeshChunk) -> None:
    fmt, n_indices, n_groups = _parse_index_header(data)
    mesh.index_format = fmt
    offset = INDEX_HEADER_SIZE
    entry_size = 4 if fmt == INDEX_FORMAT_LIST32 else 2
    indices = []
    for _ in range(n_indices):
        if entry_size == 4:
            (idx,) = struct.unpack_from("<I", data, offset)
        else:
            (idx,) = struct.unpack_from("<H", data, offset)
        indices.append(int(idx))
        offset += entry_size
    mesh.indices = indices
    groups: List[PrimitiveGroup] = []
    for i in range(n_groups):
        start_index, n_primitives, start_vertex, n_vertices = struct.unpack_from(
            "<iiii", data, offset
        )
        offset += 16
        pg = PrimitiveGroup(
            group_index=i,
            start_index=start_index,
            n_primitives=n_primitives,
            start_vertex=start_vertex,
            n_vertices=n_vertices,
        )
        if i < len(mesh.primitive_groups):
            pg.material = mesh.primitive_groups[i].material
        groups.append(pg)
    if groups:
        mesh.primitive_groups = groups


def _read_vertices(data: bytes, mesh: MeshChunk) -> None:
    fmt, n_vertices = _parse_vertex_header(data)
    mesh.vertex_format = fmt
    offset = VERTEX_HEADER_SIZE
    positions = []
    normals = []
    uvs = []
    bone_indices = []
    bone_weights = []
    for _ in range(n_vertices):
        px, py, pz = struct.unpack_from("<3f", data, offset)
        offset += 12
        if fmt == VERTEX_FORMAT_XYZNUVTB:
            packed_n, tu, tv, packed_t, packed_b = struct.unpack_from("<I2fII", data, offset)
            offset += 20
            nx, ny, nz = unpack_normal(packed_n)
            tx, ty, tz = unpack_normal(packed_t)
            bx, by, bz = unpack_normal(packed_b)
            positions.append((px, py, pz))
            normals.append((nx, ny, nz))
            uvs.append((tu, tv))
            mesh.tangents.append((tx, ty, tz))
            mesh.binormals.append((bx, by, bz))
            continue
        nx, ny, nz = struct.unpack_from("<3f", data, offset)
        offset += 12
        tu, tv = struct.unpack_from("<2f", data, offset)
        offset += 8
        positions.append((px, py, pz))
        normals.append((nx, ny, nz))
        uvs.append((tu, tv))
        if fmt in (VERTEX_FORMAT_XYZNUVIIIWW, VERTEX_FORMAT_XYZNUVIIIWWTB):
            i0, i1, i2, w0, w1, w2 = struct.unpack_from("<6B", data, offset)
            offset += 6
            bone_indices.append(_ir_bone_indices((i0, i1, i2)))
            total = max(w0 + w1 + w2, 1)
            bone_weights.append((w0 / total, w1 / total, w2 / total))
            if fmt == VERTEX_FORMAT_XYZNUVIIIWWTB:
                offset += 12
    mesh.positions = positions
    mesh.normals = normals
    mesh.uvs = uvs
    mesh.bone_indices = bone_indices
    mesh.bone_weights = bone_weights


def _section_keys(mesh: MeshChunk, suffix: str = "") -> Tuple[str, str]:
    if mesh.indices_key and mesh.vertices_key:
        return mesh.indices_key, mesh.vertices_key
    if suffix:
        return f"indices{suffix}", f"vertices{suffix}"
    return "indices", "vertices"


def read_primitives_full(path: str, mesh: MeshChunk) -> dict[str, bytes]:
    with open(path, "rb") as handle:
        data = handle.read()
    sections = read_bin_section(data)
    indices_key, vertices_key = _section_keys(mesh)
    if indices_key not in sections:
        raise KeyError(f"Missing section {indices_key!r} in {path}")
    if vertices_key not in sections:
        raise KeyError(f"Missing section {vertices_key!r} in {path}")
    _read_indices(sections[indices_key], mesh)
    _read_vertices(sections[vertices_key], mesh)
    return sections


def read_primitives_multi(path: str, mesh_chunks: Dict[str, MeshChunk]) -> dict[str, bytes]:
    with open(path, "rb") as handle:
        data = handle.read()
    sections = read_bin_section(data)
    for suffix, mesh in mesh_chunks.items():
        indices_key, vertices_key = _section_keys(mesh, suffix)
        if indices_key not in sections:
            raise KeyError(f"Missing section {indices_key!r} in {path}")
        if vertices_key not in sections:
            raise KeyError(f"Missing section {vertices_key!r} in {path}")
        _read_indices(sections[indices_key], mesh)
        _read_vertices(sections[vertices_key], mesh)
    return sections


def read_primitives(path: str, mesh: MeshChunk) -> MeshChunk:
    read_primitives_full(path, mesh)
    return mesh


def _write_indices(mesh: MeshChunk) -> bytes:
    use32 = max(mesh.indices, default=0) > 65535
    fmt = INDEX_FORMAT_LIST32 if use32 else INDEX_FORMAT_LIST
    header = bytearray()
    header.extend(fmt.encode("ascii"))
    header.extend(b"\x00" * (64 - len(fmt)))
    n_primitives = len(mesh.indices) // 3
    if not mesh.primitive_groups:
        mesh.primitive_groups = [
            PrimitiveGroup(
                group_index=0,
                start_index=0,
                n_primitives=n_primitives,
                start_vertex=0,
                n_vertices=len(mesh.positions),
            )
        ]
    header.extend(struct.pack("<ii", len(mesh.indices), len(mesh.primitive_groups)))
    body = bytearray(header)
    for idx in mesh.indices:
        if use32:
            body.extend(struct.pack("<I", idx))
        else:
            body.extend(struct.pack("<H", idx))
    for group in mesh.primitive_groups:
        body.extend(
            struct.pack(
                "<iiii",
                group.start_index,
                group.n_primitives,
                group.start_vertex,
                group.n_vertices,
            )
        )
    return bytes(body)


def _write_vertices(mesh: MeshChunk) -> bytes:
    fmt = mesh.vertex_format or VERTEX_FORMAT_XYZNUV
    header = bytearray()
    header.extend(fmt.encode("ascii"))
    header.extend(b"\x00" * (64 - len(fmt)))
    header.extend(struct.pack("<i", len(mesh.positions)))
    body = bytearray(header)
    for i, pos in enumerate(mesh.positions):
        normal = mesh.normals[i] if i < len(mesh.normals) else (0.0, 0.0, 1.0)
        uv = mesh.uvs[i] if i < len(mesh.uvs) else (0.0, 0.0)
        if fmt == VERTEX_FORMAT_XYZNUVTB:
            tangent = mesh.tangents[i] if i < len(mesh.tangents) else (1.0, 0.0, 0.0)
            binormal = mesh.binormals[i] if i < len(mesh.binormals) else (0.0, 1.0, 0.0)
            write_xyznuvtb_vertex(body, pos, uv, normal, tangent, binormal)
        else:
            body.extend(struct.pack("<3f3f2f", *pos, *normal, *uv))
        if fmt in (VERTEX_FORMAT_XYZNUVIIIWW, VERTEX_FORMAT_XYZNUVIIIWWTB):
            bind = mesh.bone_indices[i] if i < len(mesh.bone_indices) else (0, 0, 0)
            bind = _disk_bone_indices(bind)
            weights = mesh.bone_weights[i] if i < len(mesh.bone_weights) else (1.0, 0.0, 0.0)
            wbytes = [int(round(w * 255)) for w in weights[:MAX_BONE_INFLUENCES]]
            body.extend(struct.pack("<6B", *bind, *wbytes))
            if fmt == VERTEX_FORMAT_XYZNUVIIIWWTB:
                body.extend(struct.pack("<6f", 1, 0, 0, 0, 1, 0))
    return bytes(body)


def write_primitives(path: str, mesh: MeshChunk, extra_sections: dict[str, bytes] | None = None) -> None:
    sections = {
        mesh.indices_key or "indices": _write_indices(mesh),
        mesh.vertices_key or "vertices": _write_vertices(mesh),
    }
    if extra_sections:
        sections.update(extra_sections)
    data = write_bin_section(sections)
    with open(path, "wb") as handle:
        handle.write(data)


def _section_names(key: str, suffix: str) -> Tuple[str, str]:
    if not suffix:
        return "vertices", "indices"
    return f"vertices{suffix}", f"indices{suffix}"


def write_primitives_multi(path: str, mesh_chunks: Dict[str, MeshChunk], extra_sections: dict[str, bytes] | None = None) -> None:
    sections = {}
    for suffix, mesh in sorted(mesh_chunks.items(), key=lambda item: item[0]):
        vert_key, idx_key = _section_names("", suffix if suffix else "")
        if suffix:
            vert_key = f"vertices{suffix}"
            idx_key = f"indices{suffix}"
        mesh.vertices_key = vert_key
        mesh.indices_key = idx_key
        sections[idx_key] = _write_indices(mesh)
        sections[vert_key] = _write_vertices(mesh)
    if extra_sections:
        sections.update(extra_sections)
    data = write_bin_section(sections)
    with open(path, "wb") as handle:
        handle.write(data)


def compute_bounds(mesh: MeshChunk):
    if not mesh.positions:
        return (0, 0, 0), (0, 0, 0)
    xs = [p[0] for p in mesh.positions]
    ys = [p[1] for p in mesh.positions]
    zs = [p[2] for p in mesh.positions]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
