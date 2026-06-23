"""Stream animation clips one-by-one to disk (Python, no pyd bulk bundle)."""

from __future__ import annotations

import gc
import os
from dataclasses import dataclass
from typing import Any, Dict, List

from .bw_anim_plan import (
    _bake_clip_plan,
    discover_and_log_animation_clips,
)
from .bw_console import info_en
from .bw_format_core.animation_io import write_animation_binary
from .bw_format_core.ir import AnimChannel, AnimClip


@dataclass
class StreamAnimationsResult:
    warnings: List[str]
    manifest: List[Dict[str, Any]]
    clip_count: int


def animation_disk_path(res_root: str, resource_prefix: str, clip_name: str) -> str:
    rel = f"{resource_prefix}/{clip_name}".replace("\\", "/")
    return os.path.join(res_root, rel.replace("/", os.sep) + ".animation")


def animation_output_directory(res_root: str, resource_prefix: str) -> str:
    rel = resource_prefix.replace("\\", "/").strip("/")
    return os.path.join(res_root, rel.replace("/", os.sep)) if rel else res_root


def bundle_clip_to_anim_clip(clip_dict: Dict[str, Any]) -> AnimClip:
    clip = AnimClip(
        name=str(clip_dict.get("name") or "clip"),
        frame_rate=float(clip_dict.get("frame_rate") or 30.0),
    )
    for channel_dict in clip_dict.get("channels") or []:
        bone_name = str(channel_dict.get("bone_name") or "")
        if not bone_name:
            continue
        channel = AnimChannel(bone_name=bone_name)
        channel.scale_keys = [
            (float(item[0]), (float(item[1][0]), float(item[1][1]), float(item[1][2])))
            for item in channel_dict.get("scale_keys") or []
        ]
        channel.position_keys = [
            (float(item[0]), (float(item[1][0]), float(item[1][1]), float(item[1][2])))
            for item in channel_dict.get("position_keys") or []
        ]
        channel.rotation_keys = [
            (
                float(item[0]),
                (
                    float(item[1][0]),
                    float(item[1][1]),
                    float(item[1][2]),
                    float(item[1][3]),
                ),
            )
            for item in channel_dict.get("rotation_keys") or []
        ]
        if channel.position_keys:
            clip.channels.append(channel)
    return clip


def stream_animation_clips(
    arm_obj,
    skeleton: List[Dict[str, Any]],
    *,
    res_root: str,
    resource_prefix: str,
    unit_scale: float = 1.0,
    context: Any = None,
    export_all_actions: bool = True,
    animation_sample_mode: str = "KEYFRAMES",
) -> StreamAnimationsResult:
    """Bake and write one clip at a time; peak memory is O(1 clip)."""
    import bpy

    clips = discover_and_log_animation_clips(
        arm_obj,
        export_all_actions=export_all_actions,
        animation_sample_mode=animation_sample_mode,
    )
    if not clips:
        return StreamAnimationsResult(warnings=[], manifest=[], clip_count=0)

    scene = bpy.context.scene
    if context is not None and hasattr(context, "scene"):
        scene = context.scene

    arm_obj.data.pose_position = "POSE"
    original_frame = scene.frame_current
    wm = context.window_manager if context is not None else None

    warnings: List[str] = []
    manifest: List[Dict[str, Any]] = []

    info_en(f"Stream animations: {len(clips)} clips to {animation_output_directory(res_root, resource_prefix)!r}")

    if wm is not None:
        wm.progress_begin(0, len(clips))

    try:
        for index, plan in enumerate(clips):
            if wm is not None:
                wm.progress_update(index)

            info_en(
                f"Stream {index + 1}/{len(clips)}: {plan.name} "
                f"frames={plan.frame_start}-{plan.frame_end} samples={plan.frame_count}"
            )

            try:
                clip_dict = _bake_clip_plan(
                    arm_obj,
                    skeleton,
                    plan,
                    unit_scale=unit_scale,
                    scene=scene,
                )
            except Exception as exc:
                message = f"Skipped action {plan.name!r}: bake failed ({exc})"
                warnings.append(message)
                info_en(f"BW_WARN {message}")
                continue

            if clip_dict is None:
                warnings.append(f"Skipped action {plan.name!r}: bake produced no channels")
                continue

            anim_clip = bundle_clip_to_anim_clip(clip_dict)
            disk_path = animation_disk_path(res_root, resource_prefix, plan.name)
            write_animation_binary(anim_clip, disk_path)

            manifest.append(
                {
                    "name": plan.name,
                    "frame_start": plan.frame_start,
                    "frame_end": plan.frame_end,
                    "sample_count": plan.frame_count,
                    "path": disk_path.replace("\\", "/"),
                    "frame_rate": anim_clip.frame_rate,
                }
            )

            del clip_dict
            del anim_clip
            gc.collect()
    finally:
        if wm is not None:
            wm.progress_end()
        scene.frame_set(original_frame)

    info_en(f"Stream done: {len(manifest)} clips written")
    return StreamAnimationsResult(
        warnings=warnings,
        manifest=manifest,
        clip_count=len(manifest),
    )
