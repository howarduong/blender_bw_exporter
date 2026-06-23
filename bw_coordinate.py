"""Blender ↔ BigWorld axis conversion (uses active orientation from collect scope)."""

from __future__ import annotations

from typing import Iterable, Sequence

from mathutils import Matrix

from .bw_orientation import (
    CoordinateConverter,
    RowDict,
    Vec3,
    coordinate_converter_scope,
    get_coordinate_converter,
    resolve_orientation_converter,
)

__all__ = [
    "CoordinateConverter",
    "RowDict",
    "Vec3",
    "blender_matrix_to_bw_row_dict",
    "blender_to_bw_matrix",
    "blender_to_bw_vector3",
    "bw_to_blender_vector3",
    "column_matrix_from_bw_rows",
    "coordinate_converter_scope",
    "from_bw_row_dict",
    "get_coordinate_converter",
    "resolve_orientation_converter",
]


def blender_to_bw_vector3(vec: Iterable[float]) -> Vec3:
    return get_coordinate_converter().to_bw_vector3(vec)


def blender_to_bw_matrix(matrix: Matrix | Sequence[Sequence[float]]) -> Matrix:
    return get_coordinate_converter().to_bw_matrix(matrix)


def blender_matrix_to_bw_row_dict(matrix: Matrix | Sequence[Sequence[float]]) -> RowDict:
    return get_coordinate_converter().to_bw_row_dict(matrix)


def column_matrix_from_bw_rows(rows: RowDict) -> Matrix:
    return get_coordinate_converter().column_matrix_from_bw_rows(rows)


def bw_to_blender_vector3(vec: Iterable[float]) -> Vec3:
    return get_coordinate_converter().to_blender_vector3(vec)


def from_bw_row_dict(rows: RowDict) -> Matrix:
    return get_coordinate_converter().from_bw_row_dict(rows)
