"""Merge add-on preferences and export dialog into bw_export_native settings dict."""

from __future__ import annotations

from typing import Any, Dict

EXPORT_TYPE_STATIC = "STATIC"
EXPORT_TYPE_STATIC_WITH_NODES = "STATIC_WITH_NODES"
EXPORT_TYPE_ANIMATED = "ANIMATED"
EXPORT_TYPE_ANIMATION_ONLY = "ANIMATION_ONLY"


def _norm_path(path: str) -> str:
    return path.replace("\\", "/")


def _base_paths(
    *,
    model_path: str,
    resource_prefix: str,
    res_root: str,
) -> Dict[str, str]:
    return {
        "resource_prefix": _norm_path(resource_prefix),
        "res_root": _norm_path(res_root),
        "model_path": _norm_path(model_path),
    }


def build_static_settings(
    *,
    model_path: str,
    resource_prefix: str,
    res_root: str,
    export_mode: str = EXPORT_TYPE_STATIC,
    keep_existing_materials: bool = False,
    bump_mapped: bool = False,
    fix_cylindrical: bool = False,
    allow_scale: bool = False,
    snap_vertices: bool = False,
    use_legacy_orientation: bool = False,
    unit_scale: float = 1.0,
) -> Dict[str, Any]:
    if export_mode not in (EXPORT_TYPE_STATIC, EXPORT_TYPE_STATIC_WITH_NODES):
        raise ValueError(f"build_static_settings: invalid export_mode {export_mode!r}")
    return {
        **_base_paths(
            model_path=model_path,
            resource_prefix=resource_prefix,
            res_root=res_root,
        ),
        "export_mode": export_mode,
        "bump_mapped": bump_mapped,
        "fix_cylindrical": fix_cylindrical,
        "keep_existing_materials": keep_existing_materials,
        "allow_scale": allow_scale,
        "snap_vertices": snap_vertices,
        "use_legacy_orientation": use_legacy_orientation,
        "unit_scale": float(unit_scale),
    }


def build_animated_settings(
    *,
    model_path: str,
    resource_prefix: str,
    res_root: str,
    keep_existing_materials: bool = False,
    bump_mapped: bool = False,
    fix_cylindrical: bool = False,
    bone_count: int = 17,
    allow_scale: bool = False,
    snap_vertices: bool = False,
    use_legacy_orientation: bool = False,
    unit_scale: float = 1.0,
) -> Dict[str, Any]:
    return {
        **_base_paths(
            model_path=model_path,
            resource_prefix=resource_prefix,
            res_root=res_root,
        ),
        "bump_mapped": bump_mapped,
        "fix_cylindrical": fix_cylindrical,
        "bone_count": bone_count,
        "keep_existing_materials": keep_existing_materials,
        "allow_scale": allow_scale,
        "snap_vertices": snap_vertices,
        "use_legacy_orientation": use_legacy_orientation,
        "export_animations": False,
        "unit_scale": float(unit_scale),
    }


def build_export_settings(
    *,
    model_path: str,
    resource_prefix: str,
    res_root: str,
    export_type: str,
    keep_existing_materials: bool = False,
    bump_mapped: bool = False,
    fix_cylindrical: bool = False,
    bone_count: int = 17,
    allow_scale: bool = False,
    snap_vertices: bool = False,
    use_legacy_orientation: bool = False,
    unit_scale: float = 1.0,
) -> Dict[str, Any]:
    if export_type == EXPORT_TYPE_ANIMATED:
        return build_animated_settings(
            model_path=model_path,
            resource_prefix=resource_prefix,
            res_root=res_root,
            keep_existing_materials=keep_existing_materials,
            bump_mapped=bump_mapped,
            fix_cylindrical=fix_cylindrical,
            bone_count=bone_count,
            allow_scale=allow_scale,
            snap_vertices=snap_vertices,
            use_legacy_orientation=use_legacy_orientation,
            unit_scale=unit_scale,
        )
    export_mode = (
        EXPORT_TYPE_STATIC_WITH_NODES
        if export_type == EXPORT_TYPE_STATIC_WITH_NODES
        else EXPORT_TYPE_STATIC
    )
    return build_static_settings(
        model_path=model_path,
        resource_prefix=resource_prefix,
        res_root=res_root,
        export_mode=export_mode,
        keep_existing_materials=keep_existing_materials,
        bump_mapped=bump_mapped,
        fix_cylindrical=fix_cylindrical,
        allow_scale=allow_scale,
        snap_vertices=snap_vertices,
        use_legacy_orientation=use_legacy_orientation,
        unit_scale=unit_scale,
    )
