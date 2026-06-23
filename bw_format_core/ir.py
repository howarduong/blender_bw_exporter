"""BigWorld asset intermediate representation (IR).

All disk format semantics live in bw_format_core; Blender adapters must not
duplicate parsing or serialization logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class BWVector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class BWBBox:
    min: BWVector3 = field(default_factory=BWVector3)
    max: BWVector3 = field(default_factory=BWVector3)


@dataclass
class BWMaterialRef:
    identifier: str = ""
    fx_path: str = ""
    collision_flags: int = 0
    material_kind: int = 0
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PrimitiveGroup:
    group_index: int = 0
    start_index: int = 0
    n_primitives: int = 0
    start_vertex: int = 0
    n_vertices: int = 0
    material: BWMaterialRef = field(default_factory=BWMaterialRef)


@dataclass
class MeshChunk:
    """Geometry stored under BinSection keys (e.g. vertices / indices)."""

    vertices_key: str = "vertices"
    indices_key: str = "indices"
    vertex_format: str = "xyznuv"
    index_format: str = "list"
    positions: List[Tuple[float, float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    uvs: List[Tuple[float, float]] = field(default_factory=list)
    tangents: List[Tuple[float, float, float]] = field(default_factory=list)
    binormals: List[Tuple[float, float, float]] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    bone_indices: List[Tuple[int, int, int]] = field(default_factory=list)
    bone_weights: List[Tuple[float, float, float]] = field(default_factory=list)
    primitive_groups: List[PrimitiveGroup] = field(default_factory=list)
    materials: List[BWMaterialRef] = field(default_factory=list)
    triangle_material_indices: List[int] = field(default_factory=list)
    vertex_mesh_indices: List[int] = field(default_factory=list)


@dataclass
class BWNode:
    identifier: str = "Scene Root"
    transform: List[List[float]] = field(
        default_factory=lambda: [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    children: List["BWNode"] = field(default_factory=list)


@dataclass
class RenderSet:
    treat_as_world_space_object: bool = False
    node_identifier: str = "Scene Root"
    vertices_key: str = "vertices"
    indices_key: str = "indices"
    primitive_groups: List[PrimitiveGroup] = field(default_factory=list)


@dataclass
class SkeletonBone:
    name: str = ""
    parent: Optional[str] = None
    bind_matrix: List[List[float]] = field(
        default_factory=lambda: [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


@dataclass
class AnimClipRef:
    name: str = ""
    frame_rate: float = 30.0
    nodes_path: str = ""


@dataclass
class AnimChannel:
    bone_name: str = ""
    scale_keys: List[Tuple[float, Tuple[float, float, float]]] = field(default_factory=list)
    position_keys: List[Tuple[float, Tuple[float, float, float]]] = field(default_factory=list)
    rotation_keys: List[Tuple[float, Tuple[float, float, float, float]]] = field(
        default_factory=list
    )
    key_times: List[float] = field(default_factory=list)
    translations: List[Tuple[float, float, float]] = field(default_factory=list)
    rotations: List[Tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class AnimCue:
    time: float = 0.0
    name: str = ""


@dataclass
class AnimClip:
    name: str = ""
    frame_rate: float = 30.0
    channels: List[AnimChannel] = field(default_factory=list)
    cues: List[AnimCue] = field(default_factory=list)


EXPORT_TYPE_STATIC = "STATIC"
EXPORT_TYPE_ANIMATED = "ANIMATED"
EXPORT_TYPE_STATIC_WITH_NODES = "STATIC_WITH_NODES"
EXPORT_TYPE_ANIMATION_ONLY = "ANIMATION_ONLY"
EXPORT_TYPE_MESH_PARTICLES = "MESH_PARTICLES"


@dataclass
class BWAssetIR:
    """Root IR for a BigWorld model asset."""

    model_path: str = ""
    base_name: str = ""
    nodefull_visual: str = ""
    nodeless_visual: str = ""
    export_type: str = EXPORT_TYPE_STATIC
    visibility_box: BWBBox = field(default_factory=BWBBox)
    extent: float = 0.0
    root_node: BWNode = field(default_factory=BWNode)
    render_sets: List[RenderSet] = field(default_factory=list)
    mesh: MeshChunk = field(default_factory=MeshChunk)
    mesh_chunks: Dict[str, MeshChunk] = field(default_factory=dict)
    skeleton: List[SkeletonBone] = field(default_factory=list)
    animation_refs: List[AnimClipRef] = field(default_factory=list)
    animations: Dict[str, AnimClip] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    preserved_model_sections: Dict[str, str] = field(default_factory=dict)
    material_kind: int = 0
    bounding_box: BWBBox = field(default_factory=BWBBox)
    source_res_roots: List[str] = field(default_factory=list)
    lod_readonly_hints: List[str] = field(default_factory=list)
    reference_visual: str = ""
    primitive_extra_sections: Dict[str, bytes] = field(default_factory=dict)

    def visual_resource(self) -> str:
        return self.nodefull_visual or self.nodeless_visual

    def is_skinned(self) -> bool:
        if self.skeleton or self.mesh.bone_indices:
            return True
        for chunk in self.mesh_chunks.values():
            if chunk.bone_indices:
                return True
        return False

    def is_static_export(self) -> bool:
        return self.export_type in (
            EXPORT_TYPE_STATIC,
            EXPORT_TYPE_STATIC_WITH_NODES,
        )

    def sync_mesh_from_chunks(self) -> None:
        """Keep legacy single-mesh field aligned with first chunk."""
        if self.mesh_chunks:
            first_key = sorted(self.mesh_chunks.keys())[0]
            self.mesh = self.mesh_chunks[first_key]
        elif self.mesh.positions and not self.mesh_chunks:
            self.mesh_chunks = {"": self.mesh}

    def apply_visual_refs(self, resource_prefix: str) -> None:
        prefix = resource_prefix.replace("\\", "/").strip("/")
        if self.export_type == EXPORT_TYPE_STATIC:
            self.nodeless_visual = prefix
            self.nodefull_visual = ""
        elif self.export_type == EXPORT_TYPE_STATIC_WITH_NODES:
            self.nodefull_visual = prefix
            self.nodeless_visual = ""
        else:
            self.nodefull_visual = prefix
            self.nodeless_visual = ""
