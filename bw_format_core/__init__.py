"""Public BW Format Core API — load/save disk assets via IR.

Used by import (`load`) and animation stream export (`write_animation_binary`).
Production mesh export uses ``bw_export_native.pyd`` only.
"""

from __future__ import annotations

import copy
import hashlib
import os
from typing import List, Optional

from . import animation_io, model_io, primitives_io, visual_io
from .ir import BWAssetIR, BWBBox, BWVector3, EXPORT_TYPE_ANIMATION_ONLY
from .res_path import resolve_resource_path, split_res_roots


def load(model_path: str, res_roots: Optional[List[str]] = None) -> BWAssetIR:
    """Load .model and referenced .visual / .primitives / .animation into IR."""
    roots = list(res_roots or [])
    ir = model_io.read_model(model_path)
    ir.source_res_roots = roots

    visual_ref = ir.visual_resource()
    if not visual_ref:
        animation_io.load_animations_for_ir(ir, roots)
        return ir

    visual_path = resolve_resource_path(visual_ref, roots, extensions=[".visual"])
    if visual_path is None:
        candidate = os.path.splitext(model_path)[0] + ".visual"
        visual_path = candidate if os.path.isfile(candidate) else None
    if visual_path is None:
        raise FileNotFoundError(f"Cannot resolve visual for {visual_ref!r}")

    visual_io.read_visual(visual_path, ir)
    prim_path = visual_path.replace(".visual", ".primitives")
    if not os.path.isfile(prim_path):
        prim_path = resolve_resource_path(visual_ref, roots, extensions=[".primitives"])
    if prim_path and os.path.isfile(prim_path):
        if ir.mesh_chunks:
            sections = primitives_io.read_primitives_multi(prim_path, ir.mesh_chunks)
        else:
            sections = primitives_io.read_primitives_full(prim_path, ir.mesh)
        loaded_keys = set()
        chunks = ir.mesh_chunks if ir.mesh_chunks else {"": ir.mesh}
        for suffix, chunk in chunks.items():
            loaded_keys.add(chunk.indices_key or (f"indices{suffix}" if suffix else "indices"))
            loaded_keys.add(chunk.vertices_key or (f"vertices{suffix}" if suffix else "vertices"))
        ir.primitive_extra_sections = {
            k: v for k, v in sections.items() if k not in loaded_keys
        }
        ir.sync_mesh_from_chunks()
    else:
        ir.lod_readonly_hints.append("Missing .primitives file; mesh not loaded")

    animation_io.load_animations_for_ir(ir, roots)
    if len(ir.animation_refs) > 1:
        ir.lod_readonly_hints.append("Multiple animations present; LOD groups read-only")
    return ir


def save(
    ir: BWAssetIR,
    out_dir: str,
    resource_prefix: Optional[str] = None,
    model_path: Optional[str] = None,
) -> str:
    """Write IR to disk.

    When ``model_path`` is set (Blender export), the three asset files are written
    next to that path. ``resource_prefix`` is only used for XML resource ids.

    When ``model_path`` is omitted (tests/fixtures), files are laid out under
    ``out_dir`` following the dirname of ``resource_prefix``.
    """
    ir.sync_mesh_from_chunks()
    prefix = resource_prefix or ir.visual_resource() or ir.base_name
    prefix = prefix.replace("\\", "/").strip("/")
    if ir.export_type != EXPORT_TYPE_ANIMATION_ONLY:
        ir.apply_visual_refs(prefix)

    if model_path:
        model_path = os.path.normpath(os.path.abspath(model_path))
        target_dir = os.path.dirname(model_path)
        base_name = os.path.splitext(os.path.basename(model_path))[0]
    else:
        base_name = os.path.basename(prefix or ir.base_name)
        rel_dir = os.path.dirname(prefix.replace("/", os.sep)) if prefix else ""
        target_dir = os.path.join(out_dir, rel_dir) if rel_dir else out_dir
        model_path = os.path.join(target_dir, base_name + ".model")

    os.makedirs(target_dir, exist_ok=True)

    if ir.animations:
        animation_io.write_animations_for_ir(ir, out_dir, prefix)

    if ir.export_type == EXPORT_TYPE_ANIMATION_ONLY:
        model_io.write_model(ir, model_path)
        ir.model_path = model_path
        return model_path

    visual_path = os.path.join(target_dir, base_name + ".visual")
    prim_path = os.path.join(target_dir, base_name + ".primitives")

    chunks = list(ir.mesh_chunks.values()) if ir.mesh_chunks else ([ir.mesh] if ir.mesh.positions else [])
    if chunks:
        bounds_min = bounds_max = None
        for chunk in chunks:
            cmin, cmax = primitives_io.compute_bounds(chunk)
            if bounds_min is None:
                bounds_min, bounds_max = cmin, cmax
            else:
                bounds_min = tuple(min(a, b) for a, b in zip(bounds_min, cmin))
                bounds_max = tuple(max(a, b) for a, b in zip(bounds_max, cmax))
        ir.bounding_box = BWBBox(
            min=BWVector3(*bounds_min),
            max=BWVector3(*bounds_max),
        )
        if ir.extent <= 0:
            dx = bounds_max[0] - bounds_min[0]
            dy = bounds_max[1] - bounds_min[1]
            dz = bounds_max[2] - bounds_min[2]
            ir.extent = max(dx, dy, dz)
        ir.visibility_box = copy.deepcopy(ir.bounding_box)

    if len(chunks) == 1:
        ir.mesh = chunks[0]
    elif len(chunks) > 1:
        ir.mesh = chunks[0]

    visual_io.write_visual(ir, visual_path)
    extra = dict(ir.primitive_extra_sections)
    if chunks:
        if len(chunks) == 1:
            primitives_io.write_primitives(prim_path, chunks[0], extra_sections=extra or None)
        else:
            primitives_io.write_primitives_multi(prim_path, ir.mesh_chunks, extra_sections=extra or None)

    model_io.write_model(ir, model_path)
    ir.model_path = model_path
    return model_path


def save_hash(ir: BWAssetIR, out_dir: str, resource_prefix: Optional[str] = None) -> str:
    """Deterministic hash of serialized asset (POC P3)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        save(copy.deepcopy(ir), tmp, resource_prefix)
        digest = hashlib.sha256()
        for root, _, files in os.walk(tmp):
            for name in sorted(files):
                path = os.path.join(root, name)
                digest.update(name.encode("utf-8"))
                with open(path, "rb") as handle:
                    digest.update(handle.read())
        return digest.hexdigest()


from .ir import *  # noqa: F401,F403 — re-export IR types
