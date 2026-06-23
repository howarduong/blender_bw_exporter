"""BW_RES_PATH resolution for relative visual/primitives paths."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional


def split_res_roots(raw: str) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(";") if p.strip()]


def resolve_resource_path(
    relative_path: str,
    res_roots: Iterable[str],
    extensions: Optional[List[str]] = None,
) -> Optional[str]:
    """Find first existing file under res roots for a BW resource id."""
    rel = relative_path.replace("\\", "/").strip("/")
    candidates: List[str] = [rel]
    if extensions:
        for ext in extensions:
            if not rel.endswith(ext):
                candidates.append(rel + ext)

    for root in res_roots:
        root_norm = os.path.normpath(root)
        for cand in candidates:
            full = os.path.normpath(os.path.join(root_norm, cand.replace("/", os.sep)))
            if os.path.isfile(full):
                return full
    return None


def resource_id_from_path(abs_path: str, res_root: str) -> str:
    """Convert absolute path back to BW resource id (forward slashes, no ext)."""
    rel = os.path.relpath(abs_path, res_root).replace("\\", "/")
    for ext in (".model", ".visual", ".primitives", ".animation"):
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    return rel


def resource_prefix_for_export(filepath: str, res_roots: Iterable[str], fallback: str) -> tuple[str, bool]:
    """Return (visual resource id, under_res_root).

    When multiple configured roots contain the export path, prefer the outermost
    (shortest path) root so ids match engine expectations (e.g. fantasydemo/test/...).
    """
    matched = matched_res_root_for_export(filepath, res_roots)
    if matched is not None:
        model_abs = os.path.normpath(os.path.abspath(filepath))
        return resource_id_from_path(model_abs, matched), True
    return fallback, False


def matched_res_root_for_export(filepath: str, res_roots: Iterable[str]) -> Optional[str]:
    """Outermost res root containing filepath, or None."""
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
