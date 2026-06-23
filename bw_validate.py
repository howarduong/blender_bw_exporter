"""Pre-export validation (blocking errors cancel export)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

import bpy

from . import bw_native_bridge
from .bw_collect import find_armature_in_scope
from .bw_anim_plan import count_local_action_candidates
from .bw_export_ui import (
    EXPORT_KIND_ANIM_ONLY,
    EXPORT_KIND_SKINNED,
    EXPORT_KIND_STATIC,
    EXPORT_KIND_STATIC_NODES,
    count_scope_stats,
    resolve_export_config,
)
from .bw_res_path import resolve_export_paths


@dataclass
class ValidationResult:
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def validate_export(context, props, filepath: str, prefs) -> ValidationResult:
    result = ValidationResult()
    if not filepath:
        result.add_error("未指定导出路径")
        return result

    config = resolve_export_config(context, props)
    needs_pyd = config.resolved_kind != EXPORT_KIND_ANIM_ONLY
    if needs_pyd and not bw_native_bridge.is_available():
        result.add_error(bw_native_bridge.status_message())
        return result

    res_roots = prefs.get_res_roots()
    if not res_roots:
        result.add_warning("未配置 BW 资源根目录，请在插件首选项中填写 game/res")

    base = os.path.splitext(os.path.basename(filepath))[0]
    model_abs, res_root, prefix, under = resolve_export_paths(filepath, res_roots, base)
    del model_abs, prefix

    if res_roots and not under:
        result.add_error("导出路径不在 BW 资源根目录下，请保存到 game/res 子目录")

    stats = count_scope_stats(
        context,
        props.scope,
        export_all_actions=props.export_all_actions,
    )

    if config.resolved_kind in (EXPORT_KIND_STATIC, EXPORT_KIND_STATIC_NODES):
        if stats.mesh_count == 0:
            result.add_error("导出范围内没有可导出的网格对象")
    elif config.resolved_kind == EXPORT_KIND_SKINNED:
        if stats.armature_count == 0:
            result.add_error("蒙皮导出需要范围内的 Armature")
        if stats.skinned_mesh_count == 0:
            result.add_error("蒙皮导出需要至少一个带 Armature 修改器的网格")
    elif config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
        if stats.armature_count == 0:
            result.add_error("仅动画导出需要范围内的 Armature")
        visual_path = os.path.splitext(os.path.abspath(filepath))[0] + ".visual"
        if not os.path.isfile(visual_path):
            result.add_error(f"仅动画导出需要已有 .visual：{visual_path}")

    if config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
        if props.export_all_actions:
            if len(bpy.data.actions) == 0:
                result.add_error("未发现可导出的动画 Action")
        else:
            arm_obj = find_armature_in_scope(context, props.scope)
            if arm_obj is not None and count_local_action_candidates(arm_obj) == 0:
                result.add_error("未发现可导出的动画 Action")

    try:
        from .bw_orientation import resolve_orientation_converter

        resolve_orientation_converter(
            props.model_orientation,
            custom_forward=props.custom_forward,
            custom_right=props.custom_right,
            custom_up=props.custom_up,
        )
    except ValueError as exc:
        result.add_error(f"模型朝向无效：{exc}")

    del res_root
    return result
