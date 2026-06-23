"""Scene collect → MeshBundle dict for bw_export_native."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix

from .bw_build_settings import (
    EXPORT_TYPE_ANIMATED,
    EXPORT_TYPE_ANIMATION_ONLY,
    EXPORT_TYPE_STATIC,
    EXPORT_TYPE_STATIC_WITH_NODES,
)
from .bw_bind_pose import (
    bind_transform_rows,
    hierarchy_transform_rows,
    skin_init_matrix,
)
from .bw_coordinate import (
    blender_matrix_to_bw_row_dict,
    blender_to_bw_vector3,
    coordinate_converter_scope,
    resolve_orientation_converter,
)
from .bw_skin_contract import validate_skinned_bundle
from .bw_export_ui import (
    EXPORT_KIND_ANIM_ONLY,
    EXPORT_KIND_SKINNED,
    EXPORT_KIND_STATIC,
    EXPORT_KIND_STATIC_NODES,
    _is_skinned_mesh,
    _objects_for_scope,
)


def _collect_meshes(objects: List[bpy.types.Object]) -> List[bpy.types.Object]:
    return [obj for obj in objects if obj.type == "MESH" and obj.data is not None]


def _collect_armature(objects: List[bpy.types.Object]) -> Optional[bpy.types.Object]:
    for obj in objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def _default_material_fx(skinned: bool) -> str:
    if skinned:
        return "shaders/std_effects/lightonly_skinned.fx"
    return "shaders/std_effects/lightonly.fx"


def _material_from_slot(
    mat: bpy.types.Material | None,
    slot_index: int,
    *,
    skinned: bool = False,
) -> Dict[str, str]:
    default_fx = _default_material_fx(skinned)
    if mat is None:
        return {
            "identifier": f"slot_{slot_index}",
            "fx": default_fx,
            "diffuse_map": "",
        }
    fx = mat.get("bw_fx", default_fx) or default_fx
    if skinned and fx == "shaders/std_effects/lightonly.fx":
        fx = "shaders/std_effects/lightonly_skinned.fx"
    diffuse = mat.get("bw_diffuse_map", "") or ""
    return {
        "identifier": mat.get("bw_material_id", mat.name) or "default",
        "fx": fx,
        "diffuse_map": str(diffuse),
    }


def _collect_material_table(
    obj: bpy.types.Object,
    *,
    skinned: bool = False,
) -> Tuple[List[Dict[str, str]], Dict[int, int]]:
    materials: List[Dict[str, str]] = []
    slot_map: Dict[int, int] = {}
    for slot_index, slot in enumerate(obj.material_slots):
        entry = _material_from_slot(slot.material, slot_index, skinned=skinned)
        for existing_index, existing in enumerate(materials):
            if (
                existing["identifier"] == entry["identifier"]
                and existing["fx"] == entry["fx"]
                and existing["diffuse_map"] == entry["diffuse_map"]
            ):
                slot_map[slot_index] = existing_index
                break
        else:
            slot_map[slot_index] = len(materials)
            materials.append(entry)
    if not materials:
        materials.append(
            {
                "identifier": "default",
                "fx": _default_material_fx(skinned),
                "diffuse_map": "",
            }
        )
        slot_map[0] = 0
    return materials, slot_map


def _triangulate_mesh(obj: bpy.types.Object, *, bind_pose_only: bool = False):
    if bind_pose_only:
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        mesh = bpy.data.meshes.new(f"{obj.name}_bw_bind")
        bm.to_mesh(mesh)
        bm.free()
        mesh.calc_loop_triangles()
        mesh.calc_normals_split()

        def cleanup() -> None:
            if mesh.name in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)

        return mesh, cleanup

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    if not mesh.loop_triangles:
        mesh.calc_loop_triangles()

    def cleanup() -> None:
        eval_obj.to_mesh_clear()

    return mesh, cleanup


def _bw_uv_coords(u: float, v: float) -> Tuple[float, float]:
    return float(u), 1.0 - float(v)


def _ensure_armature_rest_pose(arm_obj: bpy.types.Object) -> None:
    """Use armature REST pose for bind collect (edit-bone / matrix_local data)."""
    arm_obj.data.pose_position = "REST"


def _collect_deform_bones(arm_obj: bpy.types.Object) -> List[bpy.types.Bone]:
    bones: List[bpy.types.Bone] = []
    bone_set: set[str] = set()

    def walk(bone: bpy.types.Bone) -> None:
        if bone.name in bone_set:
            return
        bone_set.add(bone.name)
        if bone.use_deform:
            bones.append(bone)
        for child in bone.children:
            walk(child)

    for bone in arm_obj.data.bones:
        if bone.parent is None:
            walk(bone)
    return bones


def _collect_weighted_bone_names(mesh_objects: List[bpy.types.Object]) -> set[str]:
    names: set[str] = set()
    for obj in mesh_objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mesh = obj.data
        group_names = [g.name for g in obj.vertex_groups]
        for vert in mesh.vertices:
            for group in vert.groups:
                if group.weight <= 0.0:
                    continue
                if 0 <= group.group < len(group_names):
                    names.add(group_names[group.group])
    return names


def _expand_bone_parent_chain(arm_data: bpy.types.Armature, bone_names: set[str]) -> set[str]:
    chain: set[str] = set()
    for name in bone_names:
        bone = arm_data.bones.get(name)
        while bone is not None:
            if bone.name in chain:
                break
            chain.add(bone.name)
            bone = bone.parent
    return chain


def _collect_skeleton(
    arm_obj: bpy.types.Object,
    *,
    required_bones: Optional[set[str]] = None,
    include_bind_matrix: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    _ensure_armature_rest_pose(arm_obj)
    skeleton: List[Dict[str, Any]] = []
    bone_index: Dict[str, int] = {}
    allowed = required_bones
    for bone in arm_obj.data.bones:
        if allowed is not None and bone.name not in allowed:
            continue
        bone_index[bone.name] = len(skeleton)
        entry: Dict[str, Any] = {
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else "",
            "transform": hierarchy_transform_rows(bone),
        }
        if include_bind_matrix:
            entry["bind_matrix"] = bind_transform_rows(bone)
        skeleton.append(entry)
    return skeleton, bone_index


def _vertex_skin_weights(
    mesh_obj: bpy.types.Object,
    vert_index: int,
    bone_index_map: Dict[str, int],
) -> Tuple[Tuple[int, int, int], Tuple[float, float, float]]:
    weights: List[Tuple[int, float]] = []
    for group in mesh_obj.vertex_groups:
        if group.name not in bone_index_map:
            continue
        try:
            weight = group.weight(vert_index)
        except RuntimeError:
            continue
        if weight > 0.0:
            weights.append((bone_index_map[group.name], float(weight)))
    weights.sort(key=lambda item: item[1], reverse=True)
    while len(weights) < 3:
        idx = weights[0][0] if weights else 0
        weights.append((idx, 0.0))
    top = weights[:3]
    total = sum(weight for _, weight in top)
    if total <= 0.0:
        return (top[0][0], top[0][0], top[0][0]), (1.0, 0.0, 0.0)
    normalized = tuple(weight / total for _, weight in top)
    return (top[0][0], top[1][0], top[2][0]), normalized


def _polygon_smoothing_group_bits(mesh: bpy.types.Mesh) -> List[int]:
    poly_count = len(mesh.polygons)
    if poly_count == 0:
        return []

    parent = list(range(poly_count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    edge_to_polys: Dict[tuple[int, int], List[int]] = {}
    for poly_index, poly in enumerate(mesh.polygons):
        for v0, v1 in poly.edge_keys:
            edge_to_polys.setdefault((v0, v1) if v0 < v1 else (v1, v0), []).append(poly_index)

    for edge in mesh.edges:
        key = edge.vertices
        edge_key = (key[0], key[1]) if key[0] < key[1] else (key[1], key[0])
        polys = edge_to_polys.get(edge_key)
        if not polys or len(polys) != 2 or edge.use_edge_sharp:
            continue
        p0, p1 = polys
        if mesh.polygons[p0].use_smooth and mesh.polygons[p1].use_smooth:
            union(p0, p1)

    root_to_bit: Dict[int, int] = {}
    bits = [0] * poly_count
    next_bit = 0
    for poly_index in range(poly_count):
        root = find(poly_index)
        if root not in root_to_bit:
            root_to_bit[root] = 1 << (next_bit % 31)
            next_bit += 1
        bits[poly_index] = root_to_bit[root]
    return bits


def _collect_static_mesh(obj: bpy.types.Object) -> Dict[str, Any]:
    mesh, cleanup_mesh = _triangulate_mesh(obj, bind_pose_only=False)
    vertex_xform = obj.matrix_world.copy()
    normal_xform = vertex_xform.to_3x3()
    materials, slot_map = _collect_material_table(obj, skinned=False)
    material_indices: List[int] = []
    try:
        positions: List[List[float]] = []
        normals: List[List[float]] = []
        uvs: List[List[float]] = []
        indices: List[int] = []
        uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
        corner_to_vert: Dict[int, int] = {}

        for tri in mesh.loop_triangles:
            tri_indices: List[int] = []
            poly = mesh.polygons[tri.polygon_index]
            mat_idx = slot_map.get(poly.material_index, 0)
            for loop_index in tri.loops:
                if loop_index in corner_to_vert:
                    tri_indices.append(corner_to_vert[loop_index])
                    continue
                loop = mesh.loops[loop_index]
                vert = mesh.vertices[loop.vertex_index]
                bw_pos = blender_to_bw_vector3(vertex_xform @ vert.co)
                normal = loop.normal
                if normal.length_squared == 0.0:
                    normal = vert.normal
                bw_normal = blender_to_bw_vector3(normal_xform @ normal)
                if bw_normal != (0.0, 0.0, 0.0):
                    nx, ny, nz = bw_normal
                    length = (nx * nx + ny * ny + nz * nz) ** 0.5
                    bw_normal = (nx / length, ny / length, nz / length)
                if uv_layer is not None:
                    uv = uv_layer[loop_index].uv
                    u, v = _bw_uv_coords(float(uv.x), float(uv.y))
                else:
                    u, v = 0.0, 0.0
                corner_to_vert[loop_index] = len(positions)
                positions.append([bw_pos[0], bw_pos[1], bw_pos[2]])
                normals.append([bw_normal[0], bw_normal[1], bw_normal[2]])
                uvs.append([u, v])
                tri_indices.append(corner_to_vert[loop_index])
            indices.extend(tri_indices)
            material_indices.append(mat_idx)

        return {
            "name": obj.name,
            "positions": positions,
            "indices": indices,
            "uvs": uvs,
            "normals": normals,
            "material": materials[0],
            "materials": materials,
            "material_indices": material_indices,
        }
    finally:
        cleanup_mesh()


def _collect_skinned_mesh(
    obj: bpy.types.Object,
    *,
    bone_index_map: Dict[str, int],
    armature_obj: bpy.types.Object,
) -> Dict[str, Any]:
    mesh, cleanup_mesh = _triangulate_mesh(obj, bind_pose_only=True)
    vertex_xform = skin_init_matrix(obj, armature_obj)
    normal_xform = vertex_xform.to_3x3()
    materials, slot_map = _collect_material_table(obj, skinned=True)
    material_indices: List[int] = []
    bone_indices: List[List[int]] = []
    bone_weights: List[List[float]] = []
    source_vertex_indices: List[int] = []
    smoothing_groups: List[int] = []
    try:
        positions: List[List[float]] = []
        normals: List[List[float]] = []
        uvs: List[List[float]] = []
        indices: List[int] = []
        poly_smoothing = _polygon_smoothing_group_bits(mesh)
        uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
        corner_to_vert: Dict[int, int] = {}

        for tri in mesh.loop_triangles:
            tri_indices: List[int] = []
            poly = mesh.polygons[tri.polygon_index]
            mat_idx = slot_map.get(poly.material_index, 0)
            for loop_index in tri.loops:
                if loop_index in corner_to_vert:
                    tri_indices.append(corner_to_vert[loop_index])
                    continue
                loop = mesh.loops[loop_index]
                vert = mesh.vertices[loop.vertex_index]
                bw_pos = blender_to_bw_vector3(vertex_xform @ vert.co)
                normal = loop.normal
                if normal.length_squared == 0.0:
                    normal = vert.normal
                bw_normal = blender_to_bw_vector3(normal_xform @ normal)
                if bw_normal != (0.0, 0.0, 0.0):
                    nx, ny, nz = bw_normal
                    length = (nx * nx + ny * ny + nz * nz) ** 0.5
                    bw_normal = (nx / length, ny / length, nz / length)
                if uv_layer is not None:
                    uv = uv_layer[loop_index].uv
                    u, v = _bw_uv_coords(float(uv.x), float(uv.y))
                else:
                    u, v = 0.0, 0.0
                bind, weights = _vertex_skin_weights(obj, loop.vertex_index, bone_index_map)
                corner_to_vert[loop_index] = len(positions)
                positions.append([bw_pos[0], bw_pos[1], bw_pos[2]])
                normals.append([bw_normal[0], bw_normal[1], bw_normal[2]])
                uvs.append([u, v])
                bone_indices.append([bind[0], bind[1], bind[2]])
                bone_weights.append([weights[0], weights[1], weights[2]])
                source_vertex_indices.append(int(vert.index))
                smoothing_groups.append(int(poly_smoothing[tri.polygon_index]))
                tri_indices.append(corner_to_vert[loop_index])
            indices.extend(tri_indices)
            material_indices.append(mat_idx)

        return {
            "name": obj.name,
            "positions": positions,
            "indices": indices,
            "uvs": uvs,
            "normals": normals,
            "material": materials[0],
            "materials": materials,
            "material_indices": material_indices,
            "bone_indices": bone_indices,
            "bone_weights": bone_weights,
            "source_vertex_indices": source_vertex_indices,
            "smoothing_groups": smoothing_groups,
        }
    finally:
        cleanup_mesh()


def _collect_mesh_entries(
    mesh_objects: List[bpy.types.Object],
    *,
    export_type: str,
    bone_index_map: Optional[Dict[str, int]] = None,
    armature_obj: Optional[bpy.types.Object] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    mesh_entries: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for obj in mesh_objects:
        if export_type == EXPORT_TYPE_ANIMATED:
            if bone_index_map is None or armature_obj is None:
                raise RuntimeError("ANIMATED collect requires bone_index_map and armature_obj")
            entry = _collect_skinned_mesh(
                obj,
                bone_index_map=bone_index_map,
                armature_obj=armature_obj,
            )
        else:
            entry = _collect_static_mesh(obj)
        if not entry.get("positions") or len(entry.get("indices", [])) < 3:
            skipped.append(obj.name)
            continue
        mesh_entries.append(entry)
    return mesh_entries, skipped


def _hardpoint_transform_matrix(obj: bpy.types.Object) -> Matrix:
    if obj.parent is not None:
        return obj.parent.matrix_world.inverted_safe() @ obj.matrix_world
    return obj.matrix_world.copy()


def _collect_hardpoint_nodes(context, scope: str) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for obj in _objects_for_scope(context, scope):
        if obj.type == "MESH":
            continue
        is_hp = bool(obj.get("bw_hardpoint")) or obj.name.startswith("HP_")
        if not is_hp:
            continue
        nodes.append(
            {
                "identifier": obj.name,
                "transform": blender_matrix_to_bw_row_dict(_hardpoint_transform_matrix(obj)),
            }
        )
    return nodes


def find_armature_in_scope(context, scope: str) -> Optional[bpy.types.Object]:
    return _collect_armature(_objects_for_scope(context, scope))


def _collect_static_bundle(context, scope: str, *, with_nodes: bool) -> Dict[str, Any]:
    scope_objects = _objects_for_scope(context, scope)
    meshes = _collect_meshes(scope_objects)
    if not meshes:
        raise RuntimeError("No exportable visual mesh objects in scope")

    mesh_entries, skipped = _collect_mesh_entries(meshes, export_type=EXPORT_TYPE_STATIC)
    if not mesh_entries:
        raise RuntimeError("No mesh geometry collected (all objects empty or invalid)")

    bundle: Dict[str, Any] = {
        "meshes": mesh_entries,
        "bsp_meshes": [],
        "hull_meshes": [],
        "portals": [],
        "nodes": _collect_hardpoint_nodes(context, scope) if with_nodes else [],
    }
    if skipped:
        bundle["export_meta"] = {"skipped_empty": skipped}
    return bundle


def _collect_skinned_bundle(
    context,
    scope: str,
    *,
    unit_scale: float,
) -> Dict[str, Any]:
    scope_objects = _objects_for_scope(context, scope)
    arm_obj = _collect_armature(scope_objects)
    if arm_obj is None:
        raise RuntimeError("Animated export requires an armature in scope")

    _ensure_armature_rest_pose(arm_obj)

    skinned_meshes = [o for o in _collect_meshes(scope_objects) if _is_skinned_mesh(o)]
    all_meshes = _collect_meshes(scope_objects)
    skipped_unskinned = [o.name for o in all_meshes if not _is_skinned_mesh(o)]
    if not skinned_meshes:
        raise RuntimeError("Animated export requires at least one skinned mesh with vertex groups")

    weighted = _collect_weighted_bone_names(skinned_meshes)
    required_bones = _expand_bone_parent_chain(arm_obj.data, weighted) if weighted else None
    skeleton, bone_index_map = _collect_skeleton(arm_obj, required_bones=required_bones)
    if not skeleton:
        raise RuntimeError("Animated export requires skeleton data")

    mesh_entries, skipped = _collect_mesh_entries(
        skinned_meshes,
        export_type=EXPORT_TYPE_ANIMATED,
        bone_index_map=bone_index_map,
        armature_obj=arm_obj,
    )
    if not mesh_entries:
        raise RuntimeError("No mesh geometry collected (all objects empty or invalid)")

    export_meta: Dict[str, Any] = {}
    if skipped_unskinned:
        export_meta["skipped_unskinned"] = skipped_unskinned
    if skipped:
        export_meta["skipped_empty"] = skipped

    bundle: Dict[str, Any] = {
        "meshes": mesh_entries,
        "bsp_meshes": [],
        "hull_meshes": [],
        "portals": [],
        "nodes": _collect_hardpoint_nodes(context, scope),
        "skeleton": skeleton,
        "animations": [],
        "export_meta": export_meta,
    }
    contract_errors = validate_skinned_bundle(bundle)
    if contract_errors:
        raise RuntimeError("MeshBundle 校验失败: " + "; ".join(contract_errors))
    return bundle


def collect_armature_skeleton_for_anim(
    context,
    scope: str,
) -> Tuple[Any, List[Dict[str, Any]]]:
    scope_objects = _objects_for_scope(context, scope)
    arm_obj = _collect_armature(scope_objects)
    if arm_obj is None:
        raise RuntimeError("Animation export requires an armature in scope")
    skeleton, _ = _collect_skeleton(arm_obj, include_bind_matrix=False)
    if not skeleton:
        raise RuntimeError("Animation export requires skeleton data")
    return arm_obj, skeleton


def resolved_kind_to_export_type(resolved_kind: str) -> str:
    if resolved_kind == EXPORT_KIND_STATIC:
        return EXPORT_TYPE_STATIC
    if resolved_kind == EXPORT_KIND_STATIC_NODES:
        return EXPORT_TYPE_STATIC_WITH_NODES
    if resolved_kind == EXPORT_KIND_SKINNED:
        return EXPORT_TYPE_ANIMATED
    if resolved_kind == EXPORT_KIND_ANIM_ONLY:
        return EXPORT_TYPE_ANIMATION_ONLY
    return EXPORT_TYPE_STATIC


def collect_scene_mesh_bundle(
    context,
    *,
    scope: str,
    resolved_kind: str,
    unit_scale: float = 1.0,
    model_orientation: str = "WOW_XFNYRZU",
    custom_forward: str = "POS_X",
    custom_right: str = "NEG_Y",
    custom_up: str = "POS_Z",
) -> Dict[str, Any]:
    converter = resolve_orientation_converter(
        model_orientation,
        custom_forward=custom_forward,
        custom_right=custom_right,
        custom_up=custom_up,
    )
    with coordinate_converter_scope(converter):
        export_type = resolved_kind_to_export_type(resolved_kind)
        if export_type == EXPORT_TYPE_ANIMATION_ONLY:
            raise RuntimeError(
                "Animation-only export uses stream_animation_clips (not collect_scene_mesh_bundle)"
            )
        elif export_type == EXPORT_TYPE_ANIMATED:
            bundle = _collect_skinned_bundle(
                context,
                scope,
                unit_scale=unit_scale,
            )
        else:
            bundle = _collect_static_bundle(
                context,
                scope,
                with_nodes=(export_type == EXPORT_TYPE_STATIC_WITH_NODES),
            )
        meta = bundle.setdefault("export_meta", {})
        meta["model_orientation"] = {
            "preset": converter.preset_id,
            "forward": converter.spec.forward,
            "right": converter.spec.right,
            "up": converter.spec.up,
            "summary": converter.summary,
        }
        return bundle
