"""Load bw_export_native.pyd and run export APIs."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, List, Optional, Tuple

from .bw_build_settings import (
    EXPORT_TYPE_ANIMATED,
    EXPORT_TYPE_ANIMATION_ONLY,
    EXPORT_TYPE_STATIC,
    EXPORT_TYPE_STATIC_WITH_NODES,
    build_export_settings,
)
from .bw_collect import collect_armature_skeleton_for_anim, collect_scene_mesh_bundle
from .bw_console import info_en

_native_module = None
_native_probe_done = False
_native_error = ""


def _addon_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _pyd_dir() -> str:
    return os.path.join(_addon_dir(), "lib", "win64")


def reset_native_probe() -> None:
    global _native_module, _native_probe_done, _native_error
    _native_module = None
    _native_probe_done = False
    _native_error = ""
    if "bw_export_native" in sys.modules:
        del sys.modules["bw_export_native"]


def _ensure_probe() -> None:
    global _native_module, _native_probe_done, _native_error
    if _native_probe_done:
        return
    _native_probe_done = True
    pyd_dir = _pyd_dir()
    if not os.path.isdir(pyd_dir):
        _native_error = f"pyd directory missing: {pyd_dir}"
        return
    if pyd_dir not in sys.path:
        sys.path.insert(0, pyd_dir)
    try:
        _native_module = importlib.import_module("bw_export_native")
    except ImportError as exc:
        _native_error = str(exc)
        _native_module = None


def _native() -> Any:
    _ensure_probe()
    if _native_module is None:
        raise RuntimeError(status_message())
    return _native_module


def is_available() -> bool:
    _ensure_probe()
    return _native_module is not None


def version() -> Optional[str]:
    _ensure_probe()
    if _native_module is None:
        return None
    try:
        return str(_native_module.version())
    except Exception as exc:
        global _native_error
        _native_error = str(exc)
        return None


def status_message() -> str:
    _ensure_probe()
    if _native_module is not None:
        ver = version() or "?"
        return f"bw_export_native {ver} 已加载"
    if _native_error:
        return f"未加载 bw_export_native：{_native_error}"
    pyd_path = os.path.join(_pyd_dir(), "bw_export_native.pyd")
    if not os.path.isfile(pyd_path):
        return f"未找到 bw_export_native.pyd — 请复制到 {pyd_path}"
    return "未加载 bw_export_native"


def _collect_warnings(bundle: dict) -> List[str]:
    warnings: List[str] = []
    meta = bundle.get("export_meta") or {}
    skipped_unskinned = meta.get("skipped_unskinned") or []
    if skipped_unskinned:
        warnings.append("Animated skipped unskinned meshes: " + ", ".join(skipped_unskinned))
    skipped_empty = meta.get("skipped_empty") or []
    if skipped_empty:
        warnings.append("Skipped empty meshes: " + ", ".join(skipped_empty))
    anim_warnings = meta.get("animation_warnings") or []
    warnings.extend(str(item) for item in anim_warnings)
    return warnings


def export_animation_stream(
    *,
    context,
    model_path: str,
    resource_prefix: str,
    res_root: str,
    scope: str = "SELECTED",
    unit_scale: float = 1.0,
    export_all_actions: bool = True,
    animation_sample_mode: str = "KEYFRAMES",
) -> Tuple[str, int, List[str]]:
    """Stream .animation files one clip at a time (Python only)."""
    from .bw_anim_stream import animation_output_directory, stream_animation_clips

    arm_obj, skeleton = collect_armature_skeleton_for_anim(context, scope)
    stream_result = stream_animation_clips(
        arm_obj,
        skeleton,
        res_root=res_root,
        resource_prefix=resource_prefix,
        unit_scale=unit_scale,
        context=context,
        export_all_actions=export_all_actions,
        animation_sample_mode=animation_sample_mode,
    )
    if stream_result.clip_count == 0:
        raise RuntimeError("Animation export produced no clips with keyframes")

    anim_dir = animation_output_directory(res_root, resource_prefix)
    info_en(f"Stream export done clips={stream_result.clip_count} dir={anim_dir}")
    return model_path, 0, list(stream_result.warnings)


def export_asset(
    *,
    context,
    model_path: str,
    resource_prefix: str,
    res_root: str,
    export_type: str,
    scope: str = "SELECTED",
    keep_existing_materials: bool = False,
    bump_mapped: bool = False,
    fix_cylindrical: bool = False,
    bone_count: int = 17,
    allow_scale: bool = False,
    snap_vertices: bool = False,
    use_legacy_orientation: bool = False,
    unit_scale: float = 1.0,
    export_all_actions: bool = True,
    animation_sample_mode: str = "KEYFRAMES",
    resolved_kind: str = "",
    model_orientation: str = "WOW_XFNYRZU",
    custom_forward: str = "POS_X",
    custom_right: str = "NEG_Y",
    custom_up: str = "POS_Z",
) -> Tuple[str, int, List[str]]:
    """Collect scene in Python, write disk via bw_export_native.pyd or stream path."""
    if export_type == EXPORT_TYPE_ANIMATION_ONLY:
        return export_animation_stream(
            context=context,
            model_path=model_path,
            resource_prefix=resource_prefix,
            res_root=res_root,
            scope=scope,
            unit_scale=unit_scale,
            export_all_actions=export_all_actions,
            animation_sample_mode=animation_sample_mode,
        )

    mod = _native()
    info_en(f"Collect scope={scope!r} kind={resolved_kind or export_type!r}")

    bundle = collect_scene_mesh_bundle(
        context,
        scope=scope,
        resolved_kind=resolved_kind or _export_type_to_kind(export_type),
        unit_scale=unit_scale,
        model_orientation=model_orientation,
        custom_forward=custom_forward,
        custom_right=custom_right,
        custom_up=custom_up,
    )
    mesh_count = len(bundle.get("meshes", []))
    export_warnings = _collect_warnings(bundle)
    info_en(f"Collect done meshes={mesh_count} skeleton={len(bundle.get('skeleton', []))}")

    settings = build_export_settings(
        model_path=model_path,
        resource_prefix=resource_prefix,
        res_root=res_root,
        export_type=export_type,
        keep_existing_materials=keep_existing_materials,
        bump_mapped=bump_mapped,
        fix_cylindrical=fix_cylindrical,
        bone_count=bone_count,
        allow_scale=allow_scale,
        snap_vertices=snap_vertices,
        use_legacy_orientation=use_legacy_orientation,
        unit_scale=unit_scale,
    )

    if hasattr(mod, "clear_export_warnings"):
        try:
            mod.clear_export_warnings()
        except Exception:
            pass

    if export_type == EXPORT_TYPE_ANIMATED:
        out_path = str(mod.export_animated(bundle, settings))
    elif export_type in (EXPORT_TYPE_STATIC, EXPORT_TYPE_STATIC_WITH_NODES):
        if mesh_count == 0:
            raise RuntimeError("Export bundle has no mesh geometry for this channel")
        out_path = str(mod.export_static(bundle, settings))
    else:
        raise NotImplementedError(f"Native export for {export_type!r} is not implemented")

    if hasattr(mod, "last_export_warnings"):
        try:
            export_warnings.extend(list(mod.last_export_warnings()))
        except Exception:
            pass
    return out_path, mesh_count, export_warnings


def embed_bsp_for_visual(res_root: str, resource_prefix: str) -> None:
    mod = _native()
    if not hasattr(mod, "embed_bsp_for_visual"):
        raise NotImplementedError("bw_export_native.embed_bsp_for_visual is not available")
    mod.embed_bsp_for_visual(res_root.replace("\\", "/"), resource_prefix.replace("\\", "/"))


def _export_type_to_kind(export_type: str) -> str:
    from .bw_export_ui import (
        EXPORT_KIND_ANIM_ONLY,
        EXPORT_KIND_SKINNED,
        EXPORT_KIND_STATIC,
        EXPORT_KIND_STATIC_NODES,
    )

    if export_type == EXPORT_TYPE_STATIC_WITH_NODES:
        return EXPORT_KIND_STATIC_NODES
    if export_type == EXPORT_TYPE_ANIMATED:
        return EXPORT_KIND_SKINNED
    if export_type == EXPORT_TYPE_ANIMATION_ONLY:
        return EXPORT_KIND_ANIM_ONLY
    return EXPORT_KIND_STATIC
