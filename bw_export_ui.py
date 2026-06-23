"""Export dialog preview and conditional UI (no collect in UI-only phase)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import bpy

EXPORT_KIND_STATIC = "STATIC"
EXPORT_KIND_STATIC_NODES = "STATIC_NODES"
EXPORT_KIND_SKINNED = "SKINNED"
EXPORT_KIND_ANIM_ONLY = "ANIM_ONLY"
EXPORT_KIND_INFER = "INFER"

PYD_API_STATIC = "export_static"
PYD_API_ANIMATED = "export_animated"
PYD_API_ANIM_STREAM = "stream_animations"

ACTION_CANDIDATE_SCAN_AT_EXPORT = -1


@dataclass
class ScopeStats:
    mesh_count: int = 0
    skinned_mesh_count: int = 0
    armature_count: int = 0
    action_candidate_count: int = 0
    hardpoint_count: int = 0


@dataclass
class ExportUiConfig:
    export_kind: str
    inferred_kind: str
    resolved_kind: str
    pyd_api: str


def _objects_for_scope(context, scope: str) -> List[bpy.types.Object]:
    if scope == "SCENE":
        return list(context.scene.objects)
    if scope == "VISIBLE":
        return [obj for obj in context.scene.objects if obj.visible_get()]
    selected = list(context.selected_objects)
    if not selected:
        return []
    result = set()
    for obj in selected:
        result.add(obj)
        for child in obj.children_recursive:
            result.add(child)
    return list(result)


def _is_skinned_mesh(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH":
        return False
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object is not None:
            return True
    return False


def _count_hardpoints(objects: List[bpy.types.Object]) -> int:
    count = 0
    for obj in objects:
        if obj.name.startswith("HP_"):
            count += 1
    return count


def count_scope_stats(
    context,
    scope: str,
    *,
    export_all_actions: bool = True,
) -> ScopeStats:
    from .bw_anim_plan import count_local_action_candidates

    objects = _objects_for_scope(context, scope)
    stats = ScopeStats()
    armatures: set[bpy.types.Object] = set()
    for obj in objects:
        if obj.type == "MESH":
            stats.mesh_count += 1
            if _is_skinned_mesh(obj):
                stats.skinned_mesh_count += 1
        elif obj.type == "ARMATURE":
            stats.armature_count += 1
            armatures.add(obj)
    stats.hardpoint_count = _count_hardpoints(objects)

    if export_all_actions:
        stats.action_candidate_count = ACTION_CANDIDATE_SCAN_AT_EXPORT
    else:
        for arm_obj in armatures:
            stats.action_candidate_count += count_local_action_candidates(arm_obj)
    return stats


def infer_export_kind(context, scope: str) -> str:
    stats = count_scope_stats(context, scope)
    if stats.skinned_mesh_count > 0 or stats.armature_count > 0:
        return EXPORT_KIND_SKINNED
    if stats.hardpoint_count > 0:
        return EXPORT_KIND_STATIC_NODES
    return EXPORT_KIND_STATIC


def resolve_export_config(context, props) -> ExportUiConfig:
    inferred = infer_export_kind(context, props.scope)
    kind = props.export_kind
    resolved = inferred if kind == EXPORT_KIND_INFER else kind

    if resolved == EXPORT_KIND_STATIC:
        pyd_api = PYD_API_STATIC
    elif resolved == EXPORT_KIND_STATIC_NODES:
        pyd_api = PYD_API_STATIC
    elif resolved == EXPORT_KIND_SKINNED:
        pyd_api = PYD_API_ANIMATED
    elif resolved == EXPORT_KIND_ANIM_ONLY:
        pyd_api = PYD_API_ANIM_STREAM
    else:
        pyd_api = PYD_API_STATIC

    return ExportUiConfig(
        export_kind=kind,
        inferred_kind=inferred,
        resolved_kind=resolved,
        pyd_api=pyd_api,
    )


def should_show_anim_box(config: ExportUiConfig) -> bool:
    return config.resolved_kind == EXPORT_KIND_ANIM_ONLY


def should_show_mesh_options(config: ExportUiConfig) -> bool:
    return config.resolved_kind != EXPORT_KIND_ANIM_ONLY


def should_show_snap_vertices(config: ExportUiConfig) -> bool:
    return config.resolved_kind in (EXPORT_KIND_STATIC, EXPORT_KIND_STATIC_NODES)


def should_show_reembed_bsp(config: ExportUiConfig) -> bool:
    return config.resolved_kind in (EXPORT_KIND_STATIC, EXPORT_KIND_STATIC_NODES)


def animation_preview_label(stats: ScopeStats, *, export_all_actions: bool) -> str:
    if stats.armature_count == 0:
        return "未发现可导出的动画 Action"
    if export_all_actions:
        if len(bpy.data.actions) == 0:
            return "未发现可导出的动画 Action"
        return "逐条写 .animation（导出时自动检测 clip 与帧范围）"
    if stats.action_candidate_count > 0:
        return f"候选 Action {stats.action_candidate_count} 个（逐条写 .animation）"
    return "未发现可导出的动画 Action"


def pyd_stats_summary_label(config: ExportUiConfig, stats: ScopeStats) -> str:
    if config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
        return pyd_stats_animation_label(stats)
    if config.resolved_kind == EXPORT_KIND_SKINNED:
        return "动画: 仅动画导出写 .animation"
    return ""


def pyd_stats_animation_label(stats: ScopeStats) -> str:
    if stats.action_candidate_count == ACTION_CANDIDATE_SCAN_AT_EXPORT:
        return "动画 导出时逐条检测（全部 Action）"
    if stats.action_candidate_count > 0:
        return f"候选 Action {stats.action_candidate_count}（导出时逐条）"
    return "动画 导出时逐条检测"


def output_description(config: ExportUiConfig, stats: ScopeStats) -> str:
    del stats
    if config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
        return ".animation × N（逐条写盘；需已有 .visual）"
    if config.resolved_kind == EXPORT_KIND_SKINNED:
        return ".model + .visual + .primitives（不含 .animation）"
    return ".model + .visual + .primitives"


def export_preview_summary(
    context,
    props,
    filepath: str = "",
) -> Dict[str, Any]:
    config = resolve_export_config(context, props)
    stats = count_scope_stats(
        context,
        props.scope,
        export_all_actions=props.export_all_actions,
    )
    inferred_label = {
        EXPORT_KIND_STATIC: "静态",
        EXPORT_KIND_STATIC_NODES: "静态（含硬点）",
        EXPORT_KIND_SKINNED: "蒙皮",
        EXPORT_KIND_ANIM_ONLY: "仅动画",
    }.get(config.inferred_kind, config.inferred_kind)
    return {
        "config": config,
        "stats": stats,
        "inferred_label": inferred_label,
        "output_description": output_description(config, stats),
        "filepath": filepath,
    }
