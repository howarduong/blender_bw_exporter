"""BW resource path helpers (Max dissolveFilename semantics for Blender UI)."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Tuple


def split_res_roots(raw: str) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]


def resource_id_from_path(abs_path: str, res_root: str) -> str:
    rel = os.path.relpath(abs_path, res_root).replace("\\", "/")
    for ext in (".model", ".visual", ".primitives", ".animation"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    return rel


def matched_res_root_for_export(filepath: str, res_roots: Iterable[str]) -> Optional[str]:
    model_abs = os.path.normpath(os.path.abspath(filepath))
    best_root: Optional[str] = None
    best_len = -1
    for root in res_roots:
        root_abs = os.path.normpath(os.path.abspath(root))
        try:
            common = os.path.commonpath([model_abs, root_abs])
        except ValueError:
            continue
        if common == root_abs:
            root_len = len(root_abs)
            if best_root is None or root_len < best_len:
                best_root = root_abs
                best_len = root_len
    return best_root


def resource_prefix_for_export(
    filepath: str,
    res_roots: Iterable[str],
    fallback: str,
) -> Tuple[str, bool]:
    matched = matched_res_root_for_export(filepath, res_roots)
    if matched is not None:
        model_abs = os.path.normpath(os.path.abspath(filepath))
        return resource_id_from_path(model_abs, matched), True
    return fallback.replace("\\", "/"), False


def resolve_export_paths(
    filepath: str,
    res_roots: Iterable[str],
    fallback_basename: str,
) -> Tuple[str, str, str, bool]:
    """Return (model_path_abs, res_root, resource_prefix, under_res_root)."""
    model_abs = os.path.normpath(os.path.abspath(filepath))
    matched = matched_res_root_for_export(filepath, res_roots)
    prefix, under = resource_prefix_for_export(filepath, res_roots, fallback_basename)
    if matched is not None:
        res_root = matched
    else:
        res_root = os.path.dirname(model_abs)
    return model_abs.replace("\\", "/"), res_root.replace("\\", "/"), prefix, under
