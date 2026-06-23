"""Max-aligned skin bind pose matrices for MeshBundle skeleton fields.

pyd: bind_matrix -> bindRow* -> Inverse -> BlendBone (export_animated.cpp).
Max: GetSkinInitTM (positions), GetBoneInitTM (bind_matrix / initialTransforms_).
"""

from __future__ import annotations

from typing import Dict, List

import bpy
from mathutils import Matrix

from .bw_coordinate import blender_matrix_to_bw_row_dict

RowDict = Dict[str, List[float]]


def skin_init_matrix(mesh_obj: bpy.types.Object, armature_obj: bpy.types.Object) -> Matrix:
    """Max GetSkinInitTM: mesh bind pose relative to armature object space."""
    if mesh_obj.parent == armature_obj:
        return mesh_obj.matrix_local.copy()
    return armature_obj.matrix_world.inverted_safe() @ mesh_obj.matrix_world


def hierarchy_transform_matrix(bone: bpy.types.Bone) -> Matrix:
    """Max MFXNode exportTree: parent-relative bone transform."""
    if bone.parent:
        return bone.parent.matrix_local.inverted() @ bone.matrix_local
    return bone.matrix_local.copy()


def bind_transform_matrix(bone: bpy.types.Bone) -> Matrix:
    """Max GetBoneInitTM: per-bone rest bind in armature space."""
    return bone.matrix_local.copy()


def is_rotation_split_child(bone: bpy.types.Bone) -> bool:
    """WoW/Max _p split: rotation bone X with parent X_p."""
    return bool(bone.parent and bone.parent.name == f"{bone.name}_p")


def hierarchy_rows_from_matrix(matrix: Matrix) -> RowDict:
    """Parent-relative TM -> P @ M @ P⁻¹ in BW row storage."""
    return blender_matrix_to_bw_row_dict(matrix)


def hierarchy_transform_rows(bone: bpy.types.Bone) -> RowDict:
    """Max MFXNode exportTree parent-relative TM + basis change."""
    return hierarchy_rows_from_matrix(hierarchy_transform_matrix(bone))


def pose_bone_local_matrix(pose_bone: bpy.types.PoseBone) -> Matrix:
    if pose_bone.parent:
        return pose_bone.parent.matrix.inverted() @ pose_bone.matrix
    return pose_bone.matrix.copy()


def pose_bone_hierarchy_rows(pose_bone: bpy.types.PoseBone) -> RowDict:
    """Animation/visual shared parent-relative rows for a pose bone."""
    return hierarchy_rows_from_matrix(pose_bone_local_matrix(pose_bone))


def bind_transform_rows(bone: bpy.types.Bone) -> RowDict:
    return blender_matrix_to_bw_row_dict(bind_transform_matrix(bone))
