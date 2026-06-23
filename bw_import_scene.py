"""Build Blender objects from BW Format Core IR (Import path)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix

from .bw_coordinate import bw_to_blender_vector3, from_bw_row_dict
from .bw_format_core.ir import BWAssetIR, BWNode, MeshChunk
from .bw_import_materials import assign_material_slots


def _matrix_from_bw_rows(rows) -> Matrix:
    if isinstance(rows, list):
        row_dict = {
            "row0": list(rows[0][:3]),
            "row1": list(rows[1][:3]),
            "row2": list(rows[2][:3]),
            "row3": list(rows[3][:3]),
        }
        return from_bw_row_dict(row_dict)
    return from_bw_row_dict(
        {
            "row0": list(rows.row0),
            "row1": list(rows.row1),
            "row2": list(rows.row2),
            "row3": list(rows.row3),
        }
    )


def _apply_node_tree(parent, node: BWNode, collection, objects: Dict[str, bpy.types.Object]):
    obj = bpy.data.objects.new(node.identifier, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.matrix_world = _matrix_from_bw_rows(node.transform)
    if node.identifier.startswith("HP_"):
        obj["bw_hardpoint"] = True
    collection.objects.link(obj)
    if parent:
        obj.parent = parent
    objects[node.identifier] = obj
    for child in node.children:
        _apply_node_tree(obj, child, collection, objects)


def _assign_primitive_group_materials(mesh_data: bpy.types.Mesh, chunk: MeshChunk) -> None:
    if not chunk.primitive_groups or not mesh_data.polygons:
        return

    slot_order: List[str] = []
    for group in chunk.primitive_groups:
        ident = group.material.identifier or "default"
        if ident not in slot_order:
            slot_order.append(ident)
    if not slot_order:
        return

    ident_to_slot = {ident: idx for idx, ident in enumerate(slot_order)}
    tri_count = len(chunk.indices) // 3
    tri_to_pg = [0] * tri_count
    for pg_idx, group in enumerate(chunk.primitive_groups):
        start_tri = group.start_index // 3
        end_tri = start_tri + group.n_primitives
        for tri_idx in range(start_tri, min(end_tri, tri_count)):
            tri_to_pg[tri_idx] = pg_idx

    for poly_idx, poly in enumerate(mesh_data.polygons):
        if poly_idx >= len(tri_to_pg):
            break
        pg_idx = tri_to_pg[poly_idx]
        if pg_idx >= len(chunk.primitive_groups):
            continue
        mat_ident = chunk.primitive_groups[pg_idx].material.identifier or "default"
        poly.material_index = ident_to_slot.get(mat_ident, 0)


def _apply_chunk_skin_weights(
    mesh_obj: bpy.types.Object,
    mesh_data: bpy.types.Mesh,
    chunk: MeshChunk,
    skeleton,
) -> None:
    if not chunk.bone_indices or not skeleton:
        return
    for v_idx, _vert in enumerate(mesh_data.vertices):
        if v_idx >= len(chunk.bone_indices):
            break
        bind = chunk.bone_indices[v_idx]
        weights = chunk.bone_weights[v_idx] if v_idx < len(chunk.bone_weights) else (1, 0, 0)
        for bone_idx, weight in zip(bind, weights):
            if weight <= 0 or bone_idx >= len(skeleton):
                continue
            name = skeleton[bone_idx].name
            if name not in mesh_obj.vertex_groups:
                mesh_obj.vertex_groups.new(name=name)
            mesh_obj.vertex_groups[name].add([v_idx], weight, "REPLACE")


def _write_chunk_normals(mesh_data: bpy.types.Mesh, chunk: MeshChunk) -> None:
    if not chunk.normals:
        return
    loop_normals = []
    for poly in mesh_data.polygons:
        for loop_idx in poly.loop_indices:
            vi = mesh_data.loops[loop_idx].vertex_index
            if vi < len(chunk.normals):
                loop_normals.append(bw_to_blender_vector3(chunk.normals[vi]))
            else:
                loop_normals.append((0.0, 0.0, 1.0))
    mesh_data.normals_split_custom_set(loop_normals)
    mesh_data.use_auto_smooth = True


def _mesh_from_chunk(ir: BWAssetIR, chunk: MeshChunk, suffix: str, res_roots: List[str]) -> bpy.types.Object:
    name = f"{ir.base_name}{suffix}" if suffix else ir.base_name
    mesh_data = bpy.data.meshes.new(f"{name}_mesh")
    mesh_obj = bpy.data.objects.new(name, mesh_data)
    faces = [tuple(chunk.indices[i : i + 3]) for i in range(0, len(chunk.indices), 3)]
    blender_positions = [bw_to_blender_vector3(p) for p in chunk.positions]
    mesh_data.from_pydata(blender_positions, [], faces)
    if chunk.uvs:
        uv_layer = mesh_data.uv_layers.new(name="UVMap")
        for poly in mesh_data.polygons:
            for loop_idx in poly.loop_indices:
                vi = mesh_data.loops[loop_idx].vertex_index
                if vi < len(chunk.uvs):
                    uv_layer.data[loop_idx].uv = chunk.uvs[vi]
    _write_chunk_normals(mesh_data, chunk)
    mesh_data.update(calc_edges=True)
    if res_roots:
        assign_material_slots(mesh_obj, chunk, res_roots)
        _assign_primitive_group_materials(mesh_data, chunk)
    return mesh_obj


def import_ir_to_scene(
    ir: BWAssetIR,
    context,
) -> Tuple[Optional[bpy.types.Object], Dict[str, bpy.types.Object]]:
    """Create mesh/armature/actions from IR."""
    collection = context.collection
    objects: Dict[str, bpy.types.Object] = {}
    res_roots = list(ir.source_res_roots or [])

    arm_obj: Optional[bpy.types.Object] = None
    if ir.skeleton:
        arm_data = bpy.data.armatures.new(f"{ir.base_name}_arm")
        arm_obj = bpy.data.objects.new(f"{ir.base_name}_armature", arm_data)
        collection.objects.link(arm_obj)
        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")
        bone_map = {}
        for bone_ir in ir.skeleton:
            edit_bone = arm_data.edit_bones.new(bone_ir.name)
            bone_map[bone_ir.name] = edit_bone
        for bone_ir in ir.skeleton:
            edit_bone = bone_map[bone_ir.name]
            if bone_ir.parent and bone_ir.parent in bone_map:
                edit_bone.parent = bone_map[bone_ir.parent]
            edit_bone.matrix = _matrix_from_bw_rows(bone_ir.bind_matrix)
            edit_bone.use_deform = True
        bpy.ops.object.mode_set(mode="OBJECT")
        objects["__armature__"] = arm_obj

    mesh_objs: List[bpy.types.Object] = []
    chunks = ir.mesh_chunks if ir.mesh_chunks else {"": ir.mesh}
    for suffix, chunk in sorted(chunks.items(), key=lambda item: item[0]):
        if not chunk.positions:
            continue
        mesh_obj = _mesh_from_chunk(ir, chunk, suffix, res_roots)
        collection.objects.link(mesh_obj)
        if arm_obj:
            mesh_obj.parent = arm_obj
            _apply_chunk_skin_weights(mesh_obj, mesh_obj.data, chunk, ir.skeleton)
            if chunk.bone_indices:
                mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
                mod.object = arm_obj
        mesh_objs.append(mesh_obj)

    mesh_obj = mesh_objs[0] if mesh_objs else None

    _apply_node_tree(None, ir.root_node, collection, objects)
    if mesh_obj:
        mesh_obj["bw_source_model"] = ir.model_path
        mesh_obj["bw_nodefull_visual"] = ir.nodefull_visual
        mesh_obj["bw_primitive_extra"] = list(ir.primitive_extra_sections.keys())

    for clip_name, _clip in ir.animations.items():
        action = bpy.data.actions.new(clip_name)
        if arm_obj:
            arm_obj.animation_data_create()
            arm_obj.animation_data.action = action

    if mesh_obj:
        context.view_layer.objects.active = mesh_obj
    return mesh_obj, objects
