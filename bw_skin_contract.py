"""MeshBundle validation for bw_export_native (export_animated contract)."""

from __future__ import annotations

from typing import Any, Dict, List


def validate_skinned_bundle(bundle: Dict[str, Any]) -> List[str]:
    """Return blocking error messages; empty list means OK."""
    errors: List[str] = []
    meshes = bundle.get("meshes") or []
    skeleton = bundle.get("skeleton") or []

    if not meshes:
        errors.append("蒙皮导出需要 meshes[]")
    if not skeleton:
        errors.append("蒙皮导出需要 skeleton[]")

    bone_names = {bone.get("name", "") for bone in skeleton}
    for mesh_index, mesh in enumerate(meshes):
        prefix = f"meshes[{mesh_index}]"
        positions = mesh.get("positions") or []
        indices = mesh.get("indices") or []
        uvs = mesh.get("uvs") or []

        if not positions:
            errors.append(f"{prefix}: positions 为空")
        if len(indices) < 3 or len(indices) % 3 != 0:
            errors.append(f"{prefix}: indices 无效")
        if uvs and len(uvs) != len(positions):
            errors.append(f"{prefix}: uvs 长度须与 positions 一致")

        corner_count = len(positions)
        for key in ("source_vertex_indices", "smoothing_groups"):
            values = mesh.get(key)
            if values is not None and len(values) != corner_count:
                errors.append(f"{prefix}: {key} 长度须与 positions 一致")

        bone_indices = mesh.get("bone_indices")
        bone_weights = mesh.get("bone_weights")
        if bone_indices is not None or bone_weights is not None:
            if bone_indices is None or bone_weights is None:
                errors.append(f"{prefix}: bone_indices 与 bone_weights 须同时提供")
            elif len(bone_indices) != corner_count or len(bone_weights) != corner_count:
                errors.append(f"{prefix}: bone_indices/bone_weights 长度须与 positions 一致")

        influences = mesh.get("bone_influences")
        if influences is not None and len(influences) != corner_count:
            errors.append(f"{prefix}: bone_influences 长度须与 positions 一致")

    for bone_index, bone in enumerate(skeleton):
        prefix = f"skeleton[{bone_index}]"
        name = bone.get("name", "")
        if not name:
            errors.append(f"{prefix}: name 为空")
        parent = bone.get("parent", "")
        if parent and parent not in bone_names:
            errors.append(f"{prefix}: parent {parent!r} 不在 skeleton 中")
        transform = bone.get("transform") or {}
        bind_matrix = bone.get("bind_matrix") or {}
        for label, block in (("transform", transform), ("bind_matrix", bind_matrix)):
            for row_key in ("row0", "row1", "row2", "row3"):
                row = block.get(row_key)
                if row is None or len(row) != 3:
                    errors.append(f"{prefix}: {label}.{row_key} 须为 3 元组")

    return errors
