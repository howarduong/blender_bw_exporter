"""BigWorld .visual XML I/O."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .ir import (
    BWAssetIR,
    BWBBox,
    BWMaterialRef,
    BWNode,
    BWVector3,
    MeshChunk,
    PrimitiveGroup,
    RenderSet,
)
from .xml_utils import read_text, sub_element


def _parse_transform(node_elem) -> list:
    t = node_elem.find("transform")
    if t is None:
        return [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
    rows = []
    for i in range(4):
        row = t.find(f"row{i}")
        parts = [float(x) for x in read_text(row, "0 0 0 0").split()]
        rows.append((parts + [0, 0, 0, 0])[:4])
    return rows


def _parse_node(node_elem) -> BWNode:
    node = BWNode(
        identifier=read_text(node_elem.find("identifier"), "Scene Root"),
        transform=_parse_transform(node_elem),
    )
    for child in node_elem.findall("node"):
        node.children.append(_parse_node(child))
    return node


def _parse_material(mat_elem) -> BWMaterialRef:
    if mat_elem is None:
        return BWMaterialRef()
    props = {}
    for prop in mat_elem.findall("property"):
        key = read_text(prop)
        tex = prop.find("Texture")
        vec4 = prop.find("Vector4")
        if tex is not None and read_text(tex):
            props[key] = read_text(tex)
        elif vec4 is not None and read_text(vec4):
            props[key] = read_text(vec4)
    return BWMaterialRef(
        identifier=read_text(mat_elem.find("identifier")),
        fx_path=read_text(mat_elem.find("fx")),
        collision_flags=int(read_text(mat_elem.find("collisionFlags"), "0") or 0),
        material_kind=int(read_text(mat_elem.find("materialKind"), "0") or 0),
        properties=props,
    )


def _parse_bbox(section) -> BWBBox:
    if section is None:
        return BWBBox()
    min_parts = [float(x) for x in read_text(section.find("min"), "0 0 0").split()]
    max_parts = [float(x) for x in read_text(section.find("max"), "0 0 0").split()]
    return BWBBox(
        min=BWVector3(*min_parts[:3]),
        max=BWVector3(*max_parts[:3]),
    )


def _geometry_suffix(vertices_key: str) -> str:
    key = vertices_key or "vertices"
    if key == "vertices":
        return ""
    if key.startswith("vertices"):
        return key[len("vertices") :]
    return key


def _chunk_for_render_set(ir: BWAssetIR, render_set: RenderSet) -> MeshChunk:
    suffix = _geometry_suffix(render_set.vertices_key)
    chunk = ir.mesh_chunks.get(suffix)
    if chunk is None:
        chunk = MeshChunk(
            vertices_key=render_set.vertices_key,
            indices_key=render_set.indices_key,
        )
        ir.mesh_chunks[suffix] = chunk
    return chunk


def _add_primitive_group(chunk: MeshChunk, group: PrimitiveGroup) -> None:
    for existing in chunk.primitive_groups:
        if existing.group_index == group.group_index:
            if not existing.material.identifier and group.material.identifier:
                existing.material = group.material
            return
    chunk.primitive_groups.append(group)


def read_visual(path: str, ir: BWAssetIR) -> BWAssetIR:
    tree = ET.parse(path)
    root = tree.getroot()
    node = root.find("node")
    if node is not None:
        ir.root_node = _parse_node(node)
    ir.material_kind = int(read_text(root.find("materialKind"), "0") or 0)
    ir.bounding_box = _parse_bbox(root.find("boundingBox"))

    ir.render_sets.clear()
    ir.mesh_chunks.clear()
    for rs in root.findall("renderSet"):
        render_set = RenderSet(
            treat_as_world_space_object=read_text(rs.find("treatAsWorldSpaceObject"), "false").lower()
            == "true",
            node_identifier=read_text(rs.find("node"), "Scene Root"),
        )
        geom = rs.find("geometry")
        if geom is not None:
            render_set.vertices_key = read_text(geom.find("vertices"), "vertices")
            render_set.indices_key = read_text(geom.find("primitive"), "indices")
            chunk = _chunk_for_render_set(ir, render_set)
            for pg in geom.findall("primitiveGroup"):
                raw = read_text(pg, "0")
                try:
                    idx = int(raw.split()[0]) if raw else 0
                except (ValueError, IndexError):
                    idx = 0
                mat = _parse_material(pg.find("material"))
                group = PrimitiveGroup(group_index=idx, material=mat)
                render_set.primitive_groups.append(group)
                _add_primitive_group(chunk, group)
        ir.render_sets.append(render_set)

    for chunk in ir.mesh_chunks.values():
        chunk.primitive_groups.sort(key=lambda group: group.group_index)
    ir.sync_mesh_from_chunks()
    return ir


def _write_transform(parent, matrix: list) -> None:
    t = ET.SubElement(parent, "transform")
    for i, row in enumerate(matrix):
        sub_element(t, f"row{i}", " ".join(f"{v:.6f}" for v in row[:3]))


def _write_material_property(parent, key: str, value: str) -> None:
    prop = ET.SubElement(parent, "property")
    prop.text = f"\t{key}\t"
    if "/" in value or value.lower().endswith((".tga", ".bmp", ".dds", ".png", ".jpg")):
        sub_element(prop, "Texture", value)
    else:
        sub_element(prop, "Vector4", value)


def _write_node(parent, node: BWNode) -> None:
    elem = ET.SubElement(parent, "node")
    sub_element(elem, "identifier", node.identifier)
    _write_transform(elem, node.transform)
    for child in node.children:
        _write_node(elem, child)


def write_visual(ir: BWAssetIR, path: str) -> None:
    tag = os.path.splitext(os.path.basename(path))[0]
    root = ET.Element(f"{tag}.visual")
    node_root = ET.SubElement(root, "node")
    sub_element(node_root, "identifier", "Scene Root")
    _write_transform(node_root, ir.root_node.transform)
    for child in ir.root_node.children:
        _write_node(node_root, child)

    sub_element(root, "materialKind", str(ir.material_kind))

    chunks = ir.mesh_chunks if ir.mesh_chunks else {"": ir.mesh}
    is_skinned = ir.is_skinned()
    for suffix, chunk in sorted(chunks.items(), key=lambda item: item[0]):
        rs = ET.SubElement(root, "renderSet")
        sub_element(rs, "treatAsWorldSpaceObject", "true" if is_skinned else "false")
        node_id = ir.render_sets[0].node_identifier if ir.render_sets else "Scene Root"
        if is_skinned and ir.skeleton:
            bone_name = ir.skeleton[0].name
            mesh_id = suffix or "0"
            node_id = f"{bone_name}BlendBone{mesh_id}"
        sub_element(rs, "node", node_id)
        geom = ET.SubElement(rs, "geometry")
        vert_key = chunk.vertices_key or ("vertices" if not suffix else f"vertices{suffix}")
        idx_key = chunk.indices_key or ("indices" if not suffix else f"indices{suffix}")
        sub_element(geom, "vertices", vert_key)
        sub_element(geom, "primitive", idx_key)
        groups = chunk.primitive_groups or ir.mesh.primitive_groups
        for group in groups:
            pg = ET.SubElement(geom, "primitiveGroup")
            pg.text = f"\t{group.group_index}\t"
            mat = ET.SubElement(pg, "material")
            sub_element(mat, "identifier", group.material.identifier)
            sub_element(mat, "fx", group.material.fx_path)
            sub_element(mat, "collisionFlags", str(group.material.collision_flags))
            sub_element(mat, "materialKind", str(group.material.material_kind))
            for key, val in group.material.properties.items():
                _write_material_property(mat, key, val)

    bb = ET.SubElement(root, "boundingBox")
    sub_element(
        bb,
        "min",
        f"{ir.bounding_box.min.x:.6f} {ir.bounding_box.min.y:.6f} {ir.bounding_box.min.z:.6f}",
    )
    sub_element(
        bb,
        "max",
        f"{ir.bounding_box.max.x:.6f} {ir.bounding_box.max.y:.6f} {ir.bounding_box.max.z:.6f}",
    )
    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tree.write(path, encoding="unicode", xml_declaration=False)


def _collect_node_names(node: BWNode, names: list) -> None:
    if node.identifier:
        names.append(node.identifier)
    for child in node.children:
        _collect_node_names(child, names)


def read_visual_node_identifiers(path: str) -> list:
    """Return node identifiers from a .visual hierarchy (reference animation export)."""
    tree = ET.parse(path)
    root = tree.getroot()
    names: list = []
    for node_elem in root.findall("node"):
        _collect_node_names(_parse_node(node_elem), names)
    return names
