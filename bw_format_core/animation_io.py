"""BigWorld .animation binary I/O (Interpolated channel type 3)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .binary_io import BinaryReader, BinaryWriter
from .ir import AnimChannel, AnimClip, AnimClipRef, AnimCue, BWAssetIR
from .xml_utils import read_text, sub_element

INTERPOLATED_COMPRESSION_OFF = 3
CUE_CHANNEL_TYPE = 6


def _build_index(keys: list) -> list:
    if not keys:
        return []
    keys.sort(key=lambda item: item[0])
    index = []
    last_time = int(keys[-1][0]) + 1
    it = 0
    for i in range(last_time + 1):
        while it < len(keys) and keys[it][0] <= i:
            it += 1
        index.append(it if it > 0 else 1)
    return index


def _channel_from_binary(reader: BinaryReader) -> AnimChannel:
    bone_name = reader.read_string()
    scale_keys = reader.read_sequence(reader.read_pair_f_vec3)
    position_keys = reader.read_sequence(reader.read_pair_f_vec3)
    rotation_keys = reader.read_sequence(reader.read_pair_f_quat)
    reader.read_sequence(reader.read_u32)
    reader.read_sequence(reader.read_u32)
    reader.read_sequence(reader.read_u32)
    channel = AnimChannel(bone_name=bone_name)
    channel.scale_keys = scale_keys
    channel.position_keys = position_keys
    channel.rotation_keys = rotation_keys
    return channel


def read_animation_binary(path: str) -> AnimClip:
    with open(path, "rb") as handle:
        data = handle.read()
    reader = BinaryReader(data)
    total_time = reader.read_f32()
    name = reader.read_string()
    reader.read_string()  # internalIdentifier
    num_channels = reader.read_i32()
    clip = AnimClip(name=name or os.path.splitext(os.path.basename(path))[0], frame_rate=30.0)
    for _ in range(num_channels):
        channel_type = reader.read_i32()
        if channel_type == INTERPOLATED_COMPRESSION_OFF:
            clip.channels.append(_channel_from_binary(reader))
        elif channel_type == CUE_CHANNEL_TYPE:
            num_cues = reader.read_i32()
            for _ in range(num_cues):
                cue_time = reader.read_f32()
                cue_name = reader.read_string()
                reader.read_i32()  # additional args count
                clip.cues.append(AnimCue(time=cue_time, name=cue_name))
        else:
            raise ValueError(f"Unsupported animation channel type {channel_type} in {path}")
    clip.frame_rate = 30.0 if total_time <= 0 else max(1.0, len(clip.channels[0].position_keys) / total_time) if clip.channels else 30.0
    return clip


def read_animation_xml(path: str) -> AnimClip:
    tree = ET.parse(path)
    root = tree.getroot()
    clip = AnimClip(
        name=os.path.splitext(os.path.basename(path))[0],
        frame_rate=float(read_text(root.find("frameRate"), "30") or 30),
    )
    for node in root.findall(".//node"):
        channel = AnimChannel(bone_name=read_text(node.find("identifier")))
        for key in node.findall("key"):
            t = float(read_text(key.find("time"), "0") or 0)
            trans = key.find("transform")
            if trans is None:
                continue
            row3 = trans.find("row3")
            if row3 is not None:
                parts = [float(x) for x in read_text(row3).split()]
                if len(parts) >= 3:
                    pos = (parts[0], parts[1], parts[2])
                    channel.position_keys.append((t, pos))
                    channel.key_times.append(t)
                    channel.translations.append(pos)
        if channel.position_keys:
            channel.scale_keys = [(channel.position_keys[0][0], (1.0, 1.0, 1.0))]
            channel.rotation_keys = [
                (channel.position_keys[0][0], (0.0, 0.0, 0.0, 1.0))
            ]
            clip.channels.append(channel)
    return clip


def read_animation(path: str) -> AnimClip:
    with open(path, "rb") as handle:
        start = handle.read(1)
    if start == b"<":
        return read_animation_xml(path)
    return read_animation_binary(path)


def load_animations_for_ir(ir: BWAssetIR, res_roots: list) -> None:
    from .res_path import resolve_resource_path

    ir.animations.clear()
    for ref in ir.animation_refs:
        path = resolve_resource_path(ref.nodes_path, res_roots, extensions=[".animation"])
        if path and os.path.isfile(path):
            ir.animations[ref.name] = read_animation(path)


def _write_channel_binary(writer: BinaryWriter, channel: AnimChannel) -> None:
    scale_keys = channel.scale_keys or [(0.0, (1.0, 1.0, 1.0))]
    position_keys = channel.position_keys
    if not position_keys and channel.translations:
        position_keys = list(zip(channel.key_times, channel.translations))
    if not position_keys:
        position_keys = [(0.0, (0.0, 0.0, 0.0))]
    rotation_keys = channel.rotation_keys
    if not rotation_keys:
        rotation_keys = [(position_keys[0][0], (0.0, 0.0, 0.0, 1.0))]

    writer.write_string(channel.bone_name)
    writer.write_sequence(scale_keys, lambda item: writer.write_pair_f_vec3(item[0], item[1]))
    writer.write_sequence(position_keys, lambda item: writer.write_pair_f_vec3(item[0], item[1]))
    writer.write_sequence(rotation_keys, lambda item: writer.write_pair_f_quat(item[0], item[1]))
    writer.write_sequence(_build_index(scale_keys), writer.write_u32)
    writer.write_sequence(_build_index(position_keys), writer.write_u32)
    writer.write_sequence(_build_index(rotation_keys), writer.write_u32)


def _write_cue_channel(writer: BinaryWriter, cues: list) -> None:
    writer.write_i32(CUE_CHANNEL_TYPE)
    writer.write_i32(len(cues))
    for cue in cues:
        writer.write_f32(cue.time)
        writer.write_string(cue.name)
        writer.write_i32(0)


def write_animation_binary(clip: AnimClip, path: str) -> None:
    writer = BinaryWriter()
    max_time = 0.0
    for channel in clip.channels:
        for keys in (channel.scale_keys, channel.position_keys, channel.rotation_keys):
            for t, _ in keys:
                max_time = max(max_time, t)
    for cue in clip.cues:
        max_time = max(max_time, cue.time)
    total_time = max_time if max_time > 0 else 1.0
    writer.write_f32(total_time)
    writer.write_string(clip.name)
    writer.write_string(clip.name)
    extra = 1 if clip.cues else 0
    writer.write_i32(len(clip.channels) + extra)
    for channel in clip.channels:
        writer.write_i32(INTERPOLATED_COMPRESSION_OFF)
        _write_channel_binary(writer, channel)
    if clip.cues:
        _write_cue_channel(writer, clip.cues)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(writer.to_bytes())


def write_animation(clip: AnimClip, path: str) -> None:
    write_animation_binary(clip, path)


def write_animations_for_ir(ir: BWAssetIR, out_dir: str, resource_prefix: str) -> None:
    ir.animation_refs.clear()
    for name, clip in ir.animations.items():
        rel = f"{resource_prefix}/{name}" if resource_prefix else name
        abs_path = os.path.join(out_dir, rel.replace("/", os.sep) + ".animation")
        write_animation_binary(clip, abs_path)
        ir.animation_refs.append(
            AnimClipRef(
                name=name,
                frame_rate=clip.frame_rate,
                nodes_path=rel,
            )
        )
