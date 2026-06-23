"""Create Blender materials from BW IR material refs (Import diffuse)."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import bpy

from .bw_format_core.ir import BWMaterialRef, MeshChunk
from .bw_format_core.res_path import resolve_resource_path


def _resolve_texture_path(tex_ref: str, res_roots: List[str]) -> Optional[str]:
    if not tex_ref:
        return None
    tex_ref = tex_ref.replace("\\", "/")
    resolved = resolve_resource_path(tex_ref, res_roots, extensions=[])
    if resolved and os.path.isfile(resolved):
        return resolved
    for root in res_roots:
        candidate = os.path.join(root, tex_ref.replace("/", os.sep))
        if os.path.isfile(candidate):
            return candidate
    return None


def _materials_from_mesh(mesh: MeshChunk) -> List[BWMaterialRef]:
    seen: Dict[str, BWMaterialRef] = {}
    for group in mesh.primitive_groups:
        mat = group.material
        if mat.identifier and mat.identifier not in seen:
            seen[mat.identifier] = mat
    return list(seen.values())


def _first_texture_property(
    mat_ref: BWMaterialRef,
    keys: Tuple[str, ...],
    res_roots: List[str],
) -> Tuple[Optional[str], Optional[str]]:
    for key in keys:
        if key not in mat_ref.properties:
            continue
        tex_path = _resolve_texture_path(mat_ref.properties[key], res_roots)
        if tex_path:
            return key, tex_path
    return None, None


def _add_image_texture_node(
    tree: bpy.types.NodeTree,
    tex_path: str,
    location: Tuple[float, float],
) -> Optional[bpy.types.ShaderNodeTexImage]:
    tex_node = tree.nodes.new("ShaderNodeTexImage")
    tex_node.location = location
    try:
        tex_node.image = bpy.data.images.load(tex_path, check_existing=True)
    except RuntimeError:
        tex_node.image = None
    return tex_node


def create_blender_material(
    mat_ref: BWMaterialRef,
    res_roots: List[str],
) -> bpy.types.Material:
    name = mat_ref.identifier or "bw_material"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    material.use_nodes = True
    material["bw_material_id"] = mat_ref.identifier or name
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    output.location = (500, 0)
    principled.location = (200, 0)
    tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    diffuse_key, diffuse_path = _first_texture_property(
        mat_ref,
        ("diffuseMap", "diffuse", "albedoMap"),
        res_roots,
    )
    if diffuse_key and mat_ref.properties.get(diffuse_key):
        material["bw_diffuse_map"] = mat_ref.properties[diffuse_key].replace("\\", "/")

    if diffuse_path:
        tex_node = _add_image_texture_node(tree, diffuse_path, (-300, 100))
        if tex_node and tex_node.image:
            tree.links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])

    _, normal_path = _first_texture_property(mat_ref, ("normalMap", "bumpMap"), res_roots)
    if normal_path:
        tex_node = _add_image_texture_node(tree, normal_path, (-300, -120))
        if tex_node and tex_node.image:
            tex_node.image.colorspace_settings.name = "Non-Color"
            normal_map = tree.nodes.new("ShaderNodeNormalMap")
            normal_map.location = (-50, -120)
            tree.links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
            tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    return material


def assign_material_slots(
    mesh_obj: bpy.types.Object,
    mesh_chunk: MeshChunk,
    res_roots: List[str],
) -> None:
    materials = _materials_from_mesh(mesh_chunk)
    if not materials:
        return
    mat_map: Dict[str, bpy.types.Material] = {}
    for mat_ref in materials:
        mat_map[mat_ref.identifier] = create_blender_material(mat_ref, res_roots)

    mesh_obj.data.materials.clear()
    order = [g.material.identifier for g in mesh_chunk.primitive_groups]
    unique_order: List[str] = []
    for ident in order:
        if ident not in unique_order:
            unique_order.append(ident)
    for ident in unique_order:
        mesh_obj.data.materials.append(mat_map.get(ident))
