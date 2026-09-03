"""Space Engineers Base6Directions, block orientation, and grid poses."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence, Tuple


Vec3 = Tuple[float, float, float]
Mat3 = Tuple[Vec3, Vec3, Vec3]
Mat4 = Tuple[Tuple[float, float, float, float], ...]

BASE6: Dict[str, Vec3] = {
    "Forward": (0.0, 0.0, -1.0),
    "Backward": (0.0, 0.0, 1.0),
    "Left": (-1.0, 0.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
    "Up": (0.0, 1.0, 0.0),
    "Down": (0.0, -1.0, 0.0),
}

_ALIASES = {
    "forward": "Forward",
    "backward": "Backward",
    "back": "Backward",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
}

# ~24 legal Base6 pairs. Recomputing this per face of a 16k hull is wasted.
_ORIENT_CACHE: Dict[Tuple[str, str], Mat3] = {}


def cell_size_meters(grid_size: str) -> float:
    return 0.5 if str(grid_size).strip().lower() == "small" else 2.5


def parse_direction(name: str, default: str = "Forward") -> Vec3:
    if not name:
        return BASE6[default]
    key = _ALIASES.get(name.strip(), name.strip())
    return BASE6.get(key, BASE6[default])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _neg(a: Vec3) -> Vec3:
    return (-a[0], -a[1], -a[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _norm(a: Vec3) -> Vec3:
    length = (_dot(a, a)) ** 0.5
    if length <= 1e-8:
        return (0.0, 0.0, 0.0)
    return _scale(a, 1.0 / length)


def orientation_matrix(forward: str = "Forward", up: str = "Up") -> Mat3:
    """
    Columns are the block's Right, Up, Backward in world (Keen) space.

    Matches MyBlockOrientation: Forward + Up define the local frame.
    """
    key = (forward or "Forward", up or "Up")
    cached = _ORIENT_CACHE.get(key)
    if cached is not None:
        return cached
    fwd = parse_direction(forward, "Forward")
    up_v = parse_direction(up, "Up")
    if abs(_dot(fwd, up_v)) > 0.9:
        up_v = parse_direction("Up") if abs(_dot(fwd, BASE6["Up"])) < 0.9 else parse_direction("Right")
    right = _norm(_cross(fwd, up_v))
    if _dot(right, right) < 1e-8:
        right = BASE6["Right"]
    true_up = _norm(_cross(right, fwd))
    backward = _neg(fwd)
    result = (right, true_up, backward)
    _ORIENT_CACHE[key] = result
    return result


def mat3_to_mat4(rotation: Mat3, translation: Vec3 = (0.0, 0.0, 0.0)) -> list:
    r, u, b = rotation
    return [
        [r[0], u[0], b[0], translation[0]],
        [r[1], u[1], b[1], translation[1]],
        [r[2], u[2], b[2], translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def identity_mat4() -> list:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mul_mat4(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list:
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
    return out


def transform_point(matrix: Sequence[Sequence[float]], point: Vec3) -> Vec3:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def transform_dir(matrix: Sequence[Sequence[float]], direction: Vec3) -> Vec3:
    x, y, z = direction
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def translation_mat4(translation: Vec3) -> list:
    m = identity_mat4()
    m[0][3] = translation[0]
    m[1][3] = translation[1]
    m[2][3] = translation[2]
    return m


def scale_mat4(sx: float, sy: float, sz: float) -> list:
    return [
        [sx, 0.0, 0.0, 0.0],
        [0.0, sy, 0.0, 0.0],
        [0.0, 0.0, sz, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def rotation_axis_mat4(axis: Vec3, radians: float) -> list:
    ax, ay, az = _norm(axis)
    if ax == ay == az == 0.0:
        return identity_mat4()
    c = _cos(radians)
    s = _sin(radians)
    t = 1.0 - c
    return [
        [t * ax * ax + c, t * ax * ay - s * az, t * ax * az + s * ay, 0.0],
        [t * ax * ay + s * az, t * ay * ay + c, t * ay * az - s * ax, 0.0],
        [t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _cos(angle: float) -> float:
    import math
    return math.cos(angle)


def _sin(angle: float) -> float:
    import math
    return math.sin(angle)


def pose_matrix(
    position: Vec3,
    forward: Vec3,
    up: Vec3,
) -> list:
    """World matrix from CubeGrid PositionAndOrientation."""
    fwd = _norm(forward)
    up_v = _norm(up)
    if _dot(fwd, fwd) < 1e-8:
        fwd = BASE6["Forward"]
    if _dot(up_v, up_v) < 1e-8:
        up_v = BASE6["Up"]
    right = _norm(_cross(fwd, up_v))
    if _dot(right, right) < 1e-8:
        right = BASE6["Right"]
    true_up = _norm(_cross(right, fwd))
    backward = _neg(fwd)
    return mat3_to_mat4((right, true_up, backward), position)


def parse_xyz_attrib(element, default: float = 0.0) -> Vec3:
    if element is None:
        return (default, default, default)
    return (
        _as_float(element.attrib.get("x"), default),
        _as_float(element.attrib.get("y"), default),
        _as_float(element.attrib.get("z"), default),
    )


def parse_xyz_children(element, default: float = 0.0) -> Vec3:
    if element is None:
        return (default, default, default)
    return (
        _child_float(element, "x", default),
        _child_float(element, "y", default),
        _child_float(element, "z", default),
    )


def _as_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _child_float(element, tag: str, default: float) -> float:
    child = element.find(tag)
    if child is None:
        child = element.find(f"{{*}}{tag}")
    if child is None or not (child.text and child.text.strip()):
        return default
    return _as_float(child.text.strip(), default)


def invert_rigid_mat4(matrix: Sequence[Sequence[float]]) -> list:
    """Invert a rigid 4x4 (rotation + translation)."""
    r00, r01, r02 = matrix[0][0], matrix[1][0], matrix[2][0]
    r10, r11, r12 = matrix[0][1], matrix[1][1], matrix[2][1]
    r20, r21, r22 = matrix[0][2], matrix[1][2], matrix[2][2]
    tx, ty, tz = matrix[0][3], matrix[1][3], matrix[2][3]
    return [
        [matrix[0][0], matrix[1][0], matrix[2][0], -(r00 * tx + r10 * ty + r20 * tz)],
        [matrix[0][1], matrix[1][1], matrix[2][1], -(r01 * tx + r11 * ty + r21 * tz)],
        [matrix[0][2], matrix[1][2], matrix[2][2], -(r02 * tx + r12 * ty + r22 * tz)],
        [0.0, 0.0, 0.0, 1.0],
    ]


def flatten_mat4(matrix: Iterable[Iterable[float]]) -> list:
    return [float(v) for row in matrix for v in row]
