"""Auto-discover Action clips and bake one clip at a time for stream export."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import bpy

from .bw_bind_pose import RowDict, is_rotation_split_child, pose_bone_hierarchy_rows
from .bw_coordinate import column_matrix_from_bw_rows
from .bw_console import info_en


@dataclass(frozen=True)
class AnimationClipPlan:
    action: bpy.types.Action
    name: str
    frame_start: int
    frame_end: int
    sample_frames: Tuple[int, ...]
    frame_count: int


def _rows_to_trs(
    rows: RowDict,
    *,
    unit_scale: float = 1.0,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]]:
    bw_matrix = column_matrix_from_bw_rows(rows)
    loc, rot, scale = bw_matrix.decompose()
    rot.normalize()
    position = (float(loc.x) * unit_scale, float(loc.y) * unit_scale, float(loc.z) * unit_scale)
    rotation = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
    scl = (float(scale.x), float(scale.y), float(scale.z))
    return position, rotation, scl


def _parse_pose_bone_name(data_path: str) -> Optional[str]:
    if data_path.startswith('pose.bones["'):
        end = data_path.find('"]', 12)
        if end > 12:
            return data_path[12:end]
    if data_path.startswith("pose.bones['"):
        end = data_path.find("']", 12)
        if end > 12:
            return data_path[12:end]
    return None


# Blender scene.frame_set() accepts signed 32-bit frame indices only.
_BLENDER_FRAME_MIN = -2_147_483_648
_BLENDER_FRAME_MAX = 2_147_483_647
# Reasonable animation frame window (WoW clips are typically well under 10k frames).
_ANIM_FRAME_MIN = -10_000
_ANIM_FRAME_MAX = 100_000
_MAX_ANIM_SPAN = 50_000


def _finite_frame_int(value: float) -> Optional[int]:
    if not math.isfinite(value):
        return None
    try:
        frame = int(round(value))
    except OverflowError:
        return None
    if frame < _BLENDER_FRAME_MIN or frame > _BLENDER_FRAME_MAX:
        return None
    return frame


def _sane_animation_frame(frame: int) -> bool:
    return _ANIM_FRAME_MIN <= frame <= _ANIM_FRAME_MAX


def _sanitize_action_bounds(
    action: bpy.types.Action,
    bounds: Tuple[int, int],
) -> Optional[Tuple[int, int]]:
    frame_start, frame_end = bounds
    if (
        _sane_animation_frame(frame_start)
        and _sane_animation_frame(frame_end)
        and frame_end >= frame_start
        and frame_end - frame_start <= _MAX_ANIM_SPAN
    ):
        return frame_start, frame_end

    alt_start = _finite_frame_int(float(action.frame_start))
    alt_end = _finite_frame_int(float(action.frame_end))
    if alt_start is None or alt_end is None or alt_end < alt_start:
        return None
    if (
        _sane_animation_frame(alt_start)
        and _sane_animation_frame(alt_end)
        and alt_end - alt_start <= _MAX_ANIM_SPAN
    ):
        return alt_start, alt_end
    return None


def _action_has_keyframes(action: bpy.types.Action) -> bool:
    for fc in action.fcurves:
        if len(fc.keyframe_points) > 0:
            return True
    return False


def _action_keyframe_bounds(action: bpy.types.Action) -> Optional[Tuple[int, int]]:
    min_frame: Optional[int] = None
    max_frame: Optional[int] = None
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            frame = _finite_frame_int(float(kp.co[0]))
            if frame is None:
                continue
            min_frame = frame if min_frame is None else min(min_frame, frame)
            max_frame = frame if max_frame is None else max(max_frame, frame)
    if min_frame is None or max_frame is None:
        return None
    return min_frame, max_frame


def _action_targets_armature(action: bpy.types.Action, arm_bone_names: set[str]) -> bool:
    for fc in action.fcurves:
        if not fc.keyframe_points:
            continue
        bone_name = _parse_pose_bone_name(fc.data_path)
        if bone_name is not None and bone_name in arm_bone_names:
            return True
    return False


def actions_for_export(
    arm_obj: bpy.types.Object,
    *,
    export_all_actions: bool = True,
) -> List[bpy.types.Action]:
    actions: List[bpy.types.Action] = []
    seen: set[str] = set()
    arm_bone_names = {bone.name for bone in arm_obj.data.bones}

    def add_action(action: bpy.types.Action | None) -> None:
        if action is None or action.name in seen:
            return
        seen.add(action.name)
        actions.append(action)

    if arm_obj.animation_data:
        add_action(arm_obj.animation_data.action)
        for track in arm_obj.animation_data.nla_tracks:
            for strip in track.strips:
                add_action(strip.action)

    if export_all_actions:
        for action in bpy.data.actions:
            if action.name in seen:
                continue
            if _action_targets_armature(action, arm_bone_names):
                add_action(action)
    return actions


def resolve_action_sample_plan(
    action: bpy.types.Action,
    *,
    animation_sample_mode: str = "KEYFRAMES",
) -> Optional[AnimationClipPlan]:
    bounds = _action_keyframe_bounds(action)
    if bounds is None:
        return None
    sanitized = _sanitize_action_bounds(action, bounds)
    if sanitized is None:
        return None
    frame_start, frame_end = sanitized

    if animation_sample_mode == "EVERY_FRAME":
        sample_frames = tuple(
            frame for frame in range(frame_start, frame_end + 1) if _sane_animation_frame(frame)
        )
    else:
        frames: set[int] = set()
        if _sane_animation_frame(frame_start):
            frames.add(frame_start)
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                frame = _finite_frame_int(float(kp.co[0]))
                if frame is None or not _sane_animation_frame(frame):
                    continue
                if frame_start <= frame <= frame_end:
                    frames.add(frame)
        if len(frames) <= 1 and _sane_animation_frame(frame_end):
            frames.add(frame_end)
        sample_frames = tuple(sorted(frames))

    if not sample_frames:
        return None
    if len(sample_frames) > _MAX_ANIM_SPAN + 1:
        return None

    return AnimationClipPlan(
        action=action,
        name=action.name,
        frame_start=min(sample_frames),
        frame_end=max(sample_frames),
        sample_frames=sample_frames,
        frame_count=len(sample_frames),
    )


def discover_animation_clips(
    arm_obj: bpy.types.Object,
    *,
    export_all_actions: bool = True,
    animation_sample_mode: str = "KEYFRAMES",
) -> List[AnimationClipPlan]:
    clips: List[AnimationClipPlan] = []
    for action in actions_for_export(arm_obj, export_all_actions=export_all_actions):
        if not _action_has_keyframes(action):
            continue
        plan = resolve_action_sample_plan(
            action,
            animation_sample_mode=animation_sample_mode,
        )
        if plan is None:
            if _action_has_keyframes(action):
                info_en(
                    f"Skipped action {action.name!r}: no valid frame range "
                    "(corrupt or out-of-range keyframe times)"
                )
            continue
        clips.append(plan)
    return clips


def count_local_action_candidates(arm_obj: bpy.types.Object) -> int:
    """Current Action + NLA strips with keyframes (cheap, no file-wide scan)."""
    count = 0
    if not arm_obj.animation_data:
        return 0
    action = arm_obj.animation_data.action
    if action is not None and _action_has_keyframes(action):
        count += 1
    seen: set[str] = {action.name} if action is not None else set()
    for track in arm_obj.animation_data.nla_tracks:
        for strip in track.strips:
            strip_action = strip.action
            if strip_action is None or strip_action.name in seen:
                continue
            seen.add(strip_action.name)
            if _action_has_keyframes(strip_action):
                count += 1
    return count


def _log_discovered_clips(
    clips: List[AnimationClipPlan],
    *,
    animation_sample_mode: str,
) -> None:
    sample_label = "keyframes" if animation_sample_mode == "KEYFRAMES" else "every_frame"
    info_en(f"Discovered {len(clips)} clips (sample={sample_label})")
    if not clips:
        return

    def log_plan(plan: AnimationClipPlan) -> None:
        info_en(
            f"  {plan.name}: frames={plan.frame_start}-{plan.frame_end} "
            f"samples={plan.frame_count}"
        )

    show_head = 5
    for plan in clips[:show_head]:
        log_plan(plan)
    remaining = len(clips) - show_head
    if remaining > 1:
        info_en(f"  … and {remaining - 1} more")
        log_plan(clips[-1])
    elif remaining == 1:
        log_plan(clips[show_head])


def discover_and_log_animation_clips(
    arm_obj: bpy.types.Object,
    *,
    export_all_actions: bool = True,
    animation_sample_mode: str = "KEYFRAMES",
) -> List[AnimationClipPlan]:
    """Export-time only: discover clip frame ranges and log manifest."""
    scope_label = "all file actions" if export_all_actions else "current/NLA actions"
    info_en(f"Discover animation clips: scanning ({scope_label}) ...")
    clips = discover_animation_clips(
        arm_obj,
        export_all_actions=export_all_actions,
        animation_sample_mode=animation_sample_mode,
    )
    _log_discovered_clips(clips, animation_sample_mode=animation_sample_mode)
    return clips


def _bind_trs_from_skeleton(
    skeleton: List[Dict[str, Any]],
) -> Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]]]:
    bind_trs: Dict[
        str,
        Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]],
    ] = {}
    for entry in skeleton:
        name = entry.get("name")
        transform = entry.get("transform")
        if not name or not transform:
            continue
        bind_trs[str(name)] = _rows_to_trs(transform, unit_scale=1.0)
    return bind_trs


def _apply_p_split_frame_trs(
    arm_data: bpy.types.Armature,
    frame_trs: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]]],
    bind_trs: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]]],
) -> None:
    for bone_name, (pos, rot, scl) in list(frame_trs.items()):
        bone = arm_data.bones.get(bone_name)
        if bone is None:
            continue
        if is_rotation_split_child(bone):
            parent_name = bone.parent.name
            parent_pos, parent_rot, parent_scl = frame_trs.get(parent_name, ((0.0, 0.0, 0.0), rot, scl))
            frame_trs[parent_name] = (
                (parent_pos[0] + pos[0], parent_pos[1] + pos[1], parent_pos[2] + pos[2]),
                parent_rot,
                parent_scl,
            )
            frame_trs[bone_name] = ((0.0, 0.0, 0.0), rot, scl)
        elif bone_name.endswith("_p") and bone_name in bind_trs:
            _, bind_rot, _ = bind_trs[bone_name]
            frame_trs[bone_name] = (pos, bind_rot, scl)


def _bake_clip_plan(
    arm_obj: bpy.types.Object,
    skeleton: List[Dict[str, Any]],
    plan: AnimationClipPlan,
    *,
    unit_scale: float,
    scene: bpy.types.Scene,
) -> Optional[Dict[str, Any]]:
    bone_names = [str(entry["name"]) for entry in skeleton if entry.get("name")]
    if not bone_names:
        return None

    bind_trs = _bind_trs_from_skeleton(skeleton)
    skeleton_rows: Dict[str, RowDict] = {
        str(entry["name"]): entry["transform"]
        for entry in skeleton
        if entry.get("name") and entry.get("transform")
    }

    if arm_obj.animation_data is None:
        arm_obj.animation_data_create()
    arm_obj.animation_data.action = plan.action

    a_start = plan.sample_frames[0]
    channel_keys: Dict[str, Dict[str, List[Any]]] = {
        bone_name: {"scale_keys": [], "position_keys": [], "rotation_keys": []}
        for bone_name in bone_names
    }

    for frame in plan.sample_frames:
        scene.frame_set(frame)
        if hasattr(bpy.context, "view_layer"):
            bpy.context.view_layer.update()
        time = float(frame - a_start)

        frame_trs: Dict[
            str,
            Tuple[Tuple[float, float, float], Tuple[float, float, float, float], Tuple[float, float, float]],
        ] = {}
        for bone_name in bone_names:
            pose_bone = arm_obj.pose.bones.get(bone_name)
            if pose_bone is None:
                continue
            rows = pose_bone_hierarchy_rows(pose_bone)
            frame_trs[bone_name] = _rows_to_trs(rows, unit_scale=unit_scale)

        if time == 0.0:
            for bone_name in bone_names:
                bind_rows = skeleton_rows.get(bone_name)
                if bind_rows is not None:
                    frame_trs[bone_name] = _rows_to_trs(bind_rows, unit_scale=unit_scale)
        else:
            _apply_p_split_frame_trs(arm_obj.data, frame_trs, bind_trs)

        for bone_name in bone_names:
            if bone_name not in frame_trs:
                continue
            pos, rot, scl = frame_trs[bone_name]
            keys = channel_keys[bone_name]
            keys["scale_keys"].append([time, [scl[0], scl[1], scl[2]]])
            keys["position_keys"].append([time, [pos[0], pos[1], pos[2]]])
            keys["rotation_keys"].append([time, [rot[0], rot[1], rot[2], rot[3]]])

    channels: List[Dict[str, Any]] = []
    for bone_name in bone_names:
        keys = channel_keys.get(bone_name)
        if keys is None or not keys["position_keys"]:
            continue
        channels.append(
            {
                "bone_name": bone_name,
                "scale_keys": keys["scale_keys"],
                "position_keys": keys["position_keys"],
                "rotation_keys": keys["rotation_keys"],
            }
        )
    if not channels:
        return None

    return {
        "name": plan.name,
        "frame_rate": float(scene.render.fps or 30),
        "channels": channels,
    }
