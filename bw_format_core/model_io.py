"""BigWorld .model XML I/O."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .ir import (
    AnimClipRef,
    BWAssetIR,
    BWBBox,
    BWVector3,
    EXPORT_TYPE_ANIMATED,
    EXPORT_TYPE_STATIC,
)
from .xml_utils import read_text, sub_element


def _parse_bbox(section) -> BWBBox:
    if section is None:
        return BWBBox()
    min_e = section.find("min")
    max_e = section.find("max")
    if min_e is None or max_e is None:
        return BWBBox()
    min_parts = [float(x) for x in read_text(min_e).split()]
    max_parts = [float(x) for x in read_text(max_e).split()]
    return BWBBox(
        min=BWVector3(*min_parts[:3]),
        max=BWVector3(*max_parts[:3]),
    )


def read_model(path: str) -> BWAssetIR:
    tree = ET.parse(path)
    root = tree.getroot()
    nodefull = read_text(root.find("nodefullVisual"))
    nodeless = read_text(root.find("nodelessVisual"))
    animation_refs = []
    for anim in root.findall("animation"):
        animation_refs.append(
            AnimClipRef(
                name=read_text(anim.find("name")),
                frame_rate=float(read_text(anim.find("frameRate"), "30") or 30),
                nodes_path=read_text(anim.find("nodes")),
            )
        )
    export_type = EXPORT_TYPE_ANIMATED if animation_refs else EXPORT_TYPE_STATIC
    ir = BWAssetIR(
        model_path=path,
        base_name=os.path.splitext(os.path.basename(path))[0],
        nodefull_visual=nodefull,
        nodeless_visual=nodeless,
        export_type=export_type,
        visibility_box=_parse_bbox(root.find("visibilityBox")),
        extent=float(read_text(root.find("extent"), "0") or 0),
    )
    ir.animation_refs = animation_refs
    for tag in ("parent",):
        elem = root.find(tag)
        if elem is not None and read_text(elem):
            ir.preserved_model_sections[tag] = read_text(elem)
    meta = root.find("metaData")
    if meta is not None:
        for child in meta:
            val = read_text(child)
            if val:
                ir.metadata[child.tag] = val
    return ir


def write_model(ir: BWAssetIR, path: str) -> None:
    tag = ir.base_name or os.path.splitext(os.path.basename(path))[0]
    root = ET.Element(f"{tag}.model")
    ET.SubElement(root, "materialNames")
    vb = ET.SubElement(root, "visibilityBox")
    sub_element(
        vb,
        "min",
        f"{ir.visibility_box.min.x:.6f} {ir.visibility_box.min.y:.6f} {ir.visibility_box.min.z:.6f}",
    )
    sub_element(
        vb,
        "max",
        f"{ir.visibility_box.max.x:.6f} {ir.visibility_box.max.y:.6f} {ir.visibility_box.max.z:.6f}",
    )
    sub_element(root, "extent", f"{ir.extent:.6f}")
    visual_ref = ir.visual_resource()
    if ir.nodeless_visual and not ir.nodefull_visual:
        sub_element(root, "nodelessVisual", visual_ref or ir.nodeless_visual)
    elif ir.nodefull_visual:
        sub_element(root, "nodefullVisual", visual_ref or ir.nodefull_visual)
    elif visual_ref:
        sub_element(root, "nodelessVisual", visual_ref)
    for ref in ir.animation_refs:
        anim = ET.SubElement(root, "animation")
        sub_element(anim, "name", ref.name)
        sub_element(anim, "frameRate", f"{ref.frame_rate:.6f}")
        sub_element(anim, "nodes", ref.nodes_path)
    if ir.metadata:
        meta = ET.SubElement(root, "metaData")
        for key, val in ir.metadata.items():
            sub_element(meta, key, val)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tree.write(path, encoding="unicode", xml_declaration=False)
