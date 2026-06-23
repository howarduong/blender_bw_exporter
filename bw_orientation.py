"""Blender model orientation → BigWorld axis conversion (collect-side)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Sequence, Tuple

from mathutils import Matrix, Vector

Vec3 = Tuple[float, float, float]
RowDict = dict[str, list[float]]

# BigWorld target (fixed): +X right, +Y up, +Z forward.
_BW_RIGHT = (1.0, 0.0, 0.0)
_BW_UP = (0.0, 1.0, 0.0)
_BW_FORWARD = (0.0, 0.0, 1.0)

AXIS_VECTORS: dict[str, Vec3] = {
    "POS_X": (1.0, 0.0, 0.0),
    "NEG_X": (-1.0, 0.0, 0.0),
    "POS_Y": (0.0, 1.0, 0.0),
    "NEG_Y": (0.0, -1.0, 0.0),
    "POS_Z": (0.0, 0.0, 1.0),
    "NEG_Z": (0.0, 0.0, -1.0),
}

ORIENTATION_PRESET_ITEMS: list[tuple[str, str, str]] = [
    (
        "WOW_XFNYRZU",
        "WoW/管线 (+X前 -Y右 +Z上)",
        "当前 Collada/WoW 角色管线默认；+X 前、-Y 右、+Z 上",
    ),
    (
        "BLENDER_YFXRZU",
        "Blender 默认 (+Y前 +X右 +Z上)",
        "Blender 常见 Y 轴朝前角色",
    ),
    (
        "BLENDER_NEG_ZFXRZU",
        "OpenGL 式 (-Z前 +X右 +Y上)",
        "-Z 前、+X 右、+Y 上（部分 FBX/引擎导入）",
    ),
    (
        "MAX_REARRANGE",
        "Max rearrange (x,z,y)",
        "旧 Max utility.cpp::rearrangeMatrix 等价；仅 golden 对比",
    ),
    (
        "CUSTOM",
        "自定义轴向",
        "手动指定前/右/上轴",
    ),
]

ORIENTATION_PRESET_IDS = {item[0] for item in ORIENTATION_PRESET_ITEMS}

AXIS_ENUM_ITEMS: list[tuple[str, str, str]] = [
    ("POS_X", "+X", "Blender 世界 +X"),
    ("NEG_X", "-X", "Blender 世界 -X"),
    ("POS_Y", "+Y", "Blender 世界 +Y"),
    ("NEG_Y", "-Y", "Blender 世界 -Y"),
    ("POS_Z", "+Z", "Blender 世界 +Z"),
    ("NEG_Z", "-Z", "Blender 世界 -Z"),
]

_PRESET_SPECS: dict[str, tuple[str, str, str]] = {
    "WOW_XFNYRZU": ("POS_X", "NEG_Y", "POS_Z"),
    "BLENDER_YFXRZU": ("POS_Y", "POS_X", "POS_Z"),
    "BLENDER_NEG_ZFXRZU": ("NEG_Z", "POS_X", "POS_Y"),
}


@dataclass(frozen=True)
class OrientationSpec:
    forward: str
    right: str
    up: str
    preset_id: str = "CUSTOM"

    def validate(self) -> None:
        axes = (self.forward, self.right, self.up)
        if len(set(axes)) != 3:
            raise ValueError("前/右/上轴必须互不相同（各选一个世界轴）")
        for axis in axes:
            if axis not in AXIS_VECTORS:
                raise ValueError(f"未知轴向: {axis!r}")

    @property
    def label(self) -> str:
        for preset_id, label, _desc in ORIENTATION_PRESET_ITEMS:
            if preset_id == self.preset_id:
                return label
        return (
            f"自定义 (前{self.forward[-2:]}, 右{self.right[-2:]}, 上{self.up[-2:]})"
        )


def _vec3(axis_id: str) -> Vec3:
    return AXIS_VECTORS[axis_id]


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _build_basis_3x3(forward: str, right: str, up: str) -> Matrix:
    f = _vec3(forward)
    r = _vec3(right)
    u = _vec3(up)
    for name, a, b in (("前", f, r), ("前", f, u), ("右", r, u)):
        if abs(_dot(a, b)) > 1e-6:
            raise ValueError(f"{name}轴与另一轴不正交，请检查自定义朝向")

    # Columns = Blender forward/right/up; map to BW forward/right/up respectively.
    b_bl = Matrix(
        [
            [f[0], r[0], u[0]],
            [f[1], r[1], u[1]],
            [f[2], r[2], u[2]],
        ]
    )
    c_bw = Matrix(
        [
            [_BW_FORWARD[0], _BW_RIGHT[0], _BW_UP[0]],
            [_BW_FORWARD[1], _BW_RIGHT[1], _BW_UP[1]],
            [_BW_FORWARD[2], _BW_RIGHT[2], _BW_UP[2]],
        ]
    )
    p3 = c_bw @ b_bl.inverted()
    return p3


def _basis_4x4(forward: str, right: str, up: str) -> Matrix:
    p3 = _build_basis_3x3(forward, right, up)
    p4 = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            p4[row][col] = p3[row][col]
    return p4


class CoordinateConverter:
    """Convert Blender vectors/matrices to BigWorld axes for one orientation spec."""

    def __init__(self, spec: OrientationSpec):
        spec.validate()
        self.spec = spec
        self.preset_id = spec.preset_id
        if spec.preset_id == "MAX_REARRANGE":
            self._legacy = True
            self._basis = Matrix.Identity(4)
            self._basis_inv = Matrix.Identity(4)
        else:
            self._legacy = False
            self._basis = _basis_4x4(spec.forward, spec.right, spec.up)
            self._basis_inv = self._basis.inverted()

    @classmethod
    def from_preset(cls, preset_id: str) -> CoordinateConverter:
        if preset_id == "CUSTOM":
            raise ValueError("CUSTOM preset requires explicit forward/right/up axes")
        if preset_id == "MAX_REARRANGE":
            return cls(OrientationSpec("POS_X", "POS_Y", "POS_Z", preset_id="MAX_REARRANGE"))
        if preset_id not in _PRESET_SPECS:
            raise ValueError(f"Unknown orientation preset: {preset_id!r}")
        forward, right, up = _PRESET_SPECS[preset_id]
        return cls(OrientationSpec(forward, right, up, preset_id=preset_id))

    @classmethod
    def from_ui(
        cls,
        preset_id: str,
        *,
        custom_forward: str = "POS_X",
        custom_right: str = "NEG_Y",
        custom_up: str = "POS_Z",
    ) -> CoordinateConverter:
        if preset_id == "CUSTOM":
            return cls(
                OrientationSpec(custom_forward, custom_right, custom_up, preset_id="CUSTOM")
            )
        return cls.from_preset(preset_id)

    @property
    def summary(self) -> str:
        if self._legacy:
            return "MAX rearrange (x,z,y)"
        return (
            f"前={self.spec.forward} 右={self.spec.right} 上={self.spec.up} "
            f"({self.spec.label})"
        )

    def to_bw_vector3(self, vec: Iterable[float]) -> Vec3:
        if self._legacy:
            x, y, z = vec
            return (float(x), float(z), float(y))
        x, y, z = vec
        out = self._basis.to_3x3() @ Vector((float(x), float(y), float(z)))
        return (float(out.x), float(out.y), float(out.z))

    def _as_matrix4(self, matrix: Matrix | Sequence[Sequence[float]]) -> Matrix:
        if isinstance(matrix, Matrix):
            return matrix.copy()
        return Matrix(matrix)

    def to_bw_matrix(self, matrix: Matrix | Sequence[Sequence[float]]) -> Matrix:
        m_bl = self._as_matrix4(matrix)
        if self._legacy:
            m4 = [[float(m_bl[row][col]) for col in range(4)] for row in range(4)]
            tx, ty, tz = m4[0][3], m4[1][3], m4[2][3]
            m4[0][3] = m4[1][3] = m4[2][3] = 0.0
            m4[3][0], m4[3][1], m4[3][2], m4[3][3] = tx, ty, tz, 1.0
            cols = [[m4[r][c] for r in range(4)] for c in range(4)]
            new_cols = [cols[0], cols[2], cols[1], cols[3]]
            mm = [[new_cols[c][r] for c in range(4)] for r in range(4)]
            mm[1], mm[2] = mm[2], mm[1]
            return Matrix(mm)
        return self._basis @ m_bl @ self._basis_inv

    def to_bw_row_dict(self, matrix: Matrix | Sequence[Sequence[float]]) -> RowDict:
        m_bw = self.to_bw_matrix(matrix)
        m_row = m_bw.transposed()
        return {
            "row0": [float(m_row[0][0]), float(m_row[0][1]), float(m_row[0][2])],
            "row1": [float(m_row[1][0]), float(m_row[1][1]), float(m_row[1][2])],
            "row2": [float(m_row[2][0]), float(m_row[2][1]), float(m_row[2][2])],
            "row3": [float(m_row[3][0]), float(m_row[3][1]), float(m_row[3][2])],
        }

    def column_matrix_from_bw_rows(self, rows: RowDict) -> Matrix:
        m_row = Matrix(
            [
                list(rows["row0"]) + [0.0],
                list(rows["row1"]) + [0.0],
                list(rows["row2"]) + [0.0],
                list(rows["row3"]) + [1.0],
            ]
        )
        return m_row.transposed()

    def to_blender_vector3(self, vec: Iterable[float]) -> Vec3:
        """BigWorld axis vector → Blender scene axis."""
        if self._legacy:
            x, y, z = vec
            return (float(x), float(z), float(y))
        v = Vector(vec)
        out = self._basis.to_3x3().inverted() @ v
        return (float(out.x), float(out.y), float(out.z))

    def from_bw_matrix(self, matrix: Matrix | Sequence[Sequence[float]]) -> Matrix:
        """BigWorld-axis column matrix → Blender column matrix."""
        m_bw = self._as_matrix4(matrix)
        if self._legacy:
            m4 = [[float(m_bw[row][col]) for col in range(4)] for row in range(4)]
            cols = [[m4[r][c] for r in range(4)] for c in range(4)]
            new_cols = [cols[0], cols[2], cols[1], cols[3]]
            mm = [[new_cols[c][r] for c in range(4)] for r in range(4)]
            mm[1], mm[2] = mm[2], mm[1]
            tx, ty, tz = mm[3][0], mm[3][1], mm[3][2]
            mm[3][0] = mm[3][1] = mm[3][2] = 0.0
            mm[0][3], mm[1][3], mm[2][3] = tx, ty, tz
            return Matrix(mm)
        return self._basis_inv @ m_bw @ self._basis

    def from_bw_row_dict(self, rows: RowDict) -> Matrix:
        return self.from_bw_matrix(self.column_matrix_from_bw_rows(rows))


_default_converter = CoordinateConverter.from_preset("WOW_XFNYRZU")
_active_converter: ContextVar[CoordinateConverter] = ContextVar(
    "bw_active_coordinate_converter",
    default=_default_converter,
)


def get_coordinate_converter() -> CoordinateConverter:
    return _active_converter.get()


@contextmanager
def coordinate_converter_scope(converter: CoordinateConverter) -> Iterator[CoordinateConverter]:
    token = _active_converter.set(converter)
    try:
        yield converter
    finally:
        _active_converter.reset(token)


def resolve_orientation_converter(
    preset_id: str,
    *,
    custom_forward: str = "POS_X",
    custom_right: str = "NEG_Y",
    custom_up: str = "POS_Z",
) -> CoordinateConverter:
    return CoordinateConverter.from_ui(
        preset_id,
        custom_forward=custom_forward,
        custom_right=custom_right,
        custom_up=custom_up,
    )
