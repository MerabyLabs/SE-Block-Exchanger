"""Orbit camera and 4x4 helpers for the preview."""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple


def look_at(eye: Sequence[float], target: Sequence[float], up: Sequence[float]) -> list:
    f = _norm(_sub(target, eye))
    s = _norm(_cross(f, up))
    u = _cross(s, f)
    return [
        [s[0], s[1], s[2], -_dot(s, eye)],
        [u[0], u[1], u[2], -_dot(u, eye)],
        [-f[0], -f[1], -f[2], _dot(f, eye)],
        [0.0, 0.0, 0.0, 1.0],
    ]


def perspective(
    fovy_deg: float,
    aspect: float,
    near: float,
    far: float,
    flip_y: bool = False,
) -> list:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    a = aspect if aspect > 1e-4 else 1.0
    fy = -f if flip_y else f
    return [
        [f / a, 0.0, 0.0, 0.0],
        [0.0, fy, 0.0, 0.0],
        [0.0, 0.0, (far + near) / (near - far), (2.0 * far * near) / (near - far)],
        [0.0, 0.0, -1.0, 0.0],
    ]


def flatten(matrix: Sequence[Sequence[float]]) -> list:
    # ModernGL wants column-major.
    return [
        matrix[0][0], matrix[1][0], matrix[2][0], matrix[3][0],
        matrix[0][1], matrix[1][1], matrix[2][1], matrix[3][1],
        matrix[0][2], matrix[1][2], matrix[2][2], matrix[3][2],
        matrix[0][3], matrix[1][3], matrix[2][3], matrix[3][3],
    ]


def flatten_row(matrix: Sequence[Sequence[float]]) -> list:
    return [float(v) for row in matrix for v in row]


PREVIEW_FOVY_DEG = 50.0


def aabb_center_radius(
    aabb_min: Sequence[float],
    aabb_max: Sequence[float],
) -> Tuple[Tuple[float, float, float], float]:
    """AABB center and bounding-sphere radius (half diagonal)."""
    lo = (float(aabb_min[0]), float(aabb_min[1]), float(aabb_min[2]))
    hi = (float(aabb_max[0]), float(aabb_max[1]), float(aabb_max[2]))
    if hi[0] < lo[0] or hi[1] < lo[1] or hi[2] < lo[2]:
        return (0.0, 0.0, 0.0), 10.0
    center = ((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, (lo[2] + hi[2]) * 0.5)
    dx, dy, dz = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
    radius = max(0.5 * (dx * dx + dy * dy + dz * dz) ** 0.5, 2.5)
    return center, radius


def fit_distance(
    radius: float,
    fovy_deg: float = PREVIEW_FOVY_DEG,
    fill: float = 0.88,
) -> float:
    """Orbit distance so a sphere of `radius` fills `fill` of the vertical FOV."""
    r = max(2.5, float(radius))
    fill = min(0.98, max(0.35, float(fill)))
    return max(6.0, r / math.tan(math.radians(float(fovy_deg)) * 0.5) / fill)


def clip_planes_from_aabb(
    eye: Sequence[float],
    aabb_min: Sequence[float],
    aabb_max: Sequence[float],
    *,
    min_near: float = 0.15,
    padding: float = 1.18,
    target: Optional[Sequence[float]] = None,
    radius: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Perspective near/far that includes the whole AABB (and the framed sphere).

    Near scales with hull size so a 500 m ship never uses a 0.001 near plane.
    A stale tiny AABB cannot clip a hull the orbit target still frames.
    """
    ex, ey, ez = float(eye[0]), float(eye[1]), float(eye[2])
    lo = (float(aabb_min[0]), float(aabb_min[1]), float(aabb_min[2]))
    hi = (float(aabb_max[0]), float(aabb_max[1]), float(aabb_max[2]))
    if hi[0] < lo[0] or hi[1] < lo[1] or hi[2] < lo[2]:
        lo, hi = (-4.0, -4.0, -4.0), (4.0, 4.0, 4.0)

    cx = min(max(ex, lo[0]), hi[0])
    cy = min(max(ey, lo[1]), hi[1])
    cz = min(max(ez, lo[2]), hi[2])
    closest = ((cx - ex) ** 2 + (cy - ey) ** 2 + (cz - ez) ** 2) ** 0.5

    farthest = 0.0
    for x in (lo[0], hi[0]):
        for y in (lo[1], hi[1]):
            for z in (lo[2], hi[2]):
                d = ((x - ex) ** 2 + (y - ey) ** 2 + (z - ez) ** 2) ** 0.5
                if d > farthest:
                    farthest = d

    diag = (
        (hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2 + (hi[2] - lo[2]) ** 2
    ) ** 0.5
    size_near = max(float(min_near), diag * 0.0004)

    if closest < 0.35:
        near = max(size_near, farthest / 500.0)
    else:
        near = max(size_near, closest * 0.5)
    far = max(near + max(6.0, diag * 0.08), farthest * float(padding))

    if target is not None:
        tx, ty, tz = float(target[0]), float(target[1]), float(target[2])
        dist = ((tx - ex) ** 2 + (ty - ey) ** 2 + (tz - ez) ** 2) ** 0.5
        rad = max(2.5, float(radius) if radius is not None else diag * 0.5)
        far = max(far, dist + rad * 1.25)
        if dist > rad * 0.15:
            near = min(near, max(size_near, dist - rad * 1.15))

    if far / max(near, 1e-6) > 8000.0:
        near = far / 8000.0
    return near, far


def clip_planes_for_view(
    distance: float,
    radius: float,
    *,
    min_near: float = 0.15,
) -> Tuple[float, float]:
    """Sphere-framed clip range (camera looks at origin from +Z)."""
    radius = max(1.0, float(radius))
    distance = max(min_near, float(distance))
    return clip_planes_from_aabb(
        (0.0, 0.0, distance),
        (-radius, -radius, -radius),
        (radius, radius, radius),
        min_near=min_near,
        target=(0.0, 0.0, 0.0),
        radius=radius,
    )


def _sub(a, b) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a) -> Tuple[float, float, float]:
    length = math.sqrt(_dot(a, a))
    if length < 1e-8:
        return (0.0, 0.0, 1.0)
    return (a[0] / length, a[1] / length, a[2] / length)


PITCH_LIMIT = 1.2
ZOOM_MIN = 2.0
ZOOM_MAX = 80000.0


def wheel_zoom_inward(
    delta: Optional[float] = None,
    button: Optional[int] = None,
) -> Optional[bool]:
    """
    Decode a mouse-wheel event into zoom direction.

    True = zoom in, False = zoom out, None = not a zoom notch.
    Windows/macOS MouseWheel: positive delta is inward.
    X11 Button-4 is inward, Button-5 is outward.
    """
    if button == 4:
        return True
    if button == 5:
        return False
    if delta is None:
        return None
    try:
        amount = float(delta)
    except (TypeError, ValueError):
        return None
    if amount == 0.0:
        return None
    return amount > 0.0


def zoom_factor_for_distance(distance: float, zoom_in: bool) -> float:
    """Log / distance-scaled notch: finer near a block, coarser at hull scale."""
    dist = max(ZOOM_MIN, float(distance))
    t = math.log(dist / ZOOM_MIN) / math.log(ZOOM_MAX / ZOOM_MIN)
    step = 0.055 + 0.17 * max(0.0, min(1.0, t))
    return (1.0 - step) if zoom_in else (1.0 + step)


def zoom_toward_target(
    target: Sequence[float],
    point: Sequence[float],
    factor: float,
) -> Tuple[float, float, float]:
    """Slide the orbit pivot toward `point` when zooming in (factor < 1)."""
    blend = 1.0 - float(factor)
    if blend <= 0.0:
        return (float(target[0]), float(target[1]), float(target[2]))
    blend = max(0.0, min(0.85, blend))
    return (
        float(target[0]) + (float(point[0]) - float(target[0])) * blend,
        float(target[1]) + (float(point[1]) - float(target[1])) * blend,
        float(target[2]) + (float(point[2]) - float(target[2])) * blend,
    )


class OrbitCamera:
    def __init__(self) -> None:
        self.target = [0.0, 0.0, 0.0]
        self.distance = 40.0
        self.yaw = 0.6
        self.pitch = 0.45
        self.zoom_min = ZOOM_MIN
        self.zoom_max = ZOOM_MAX

    def eye(self) -> Tuple[float, float, float]:
        cp = math.cos(self.pitch)
        x = self.target[0] + self.distance * cp * math.sin(self.yaw)
        y = self.target[1] + self.distance * math.sin(self.pitch)
        z = self.target[2] + self.distance * cp * math.cos(self.yaw)
        return (x, y, z)

    def view_matrix(self) -> list:
        return look_at(self.eye(), self.target, (0.0, 1.0, 0.0))

    def basis(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """Forward (toward target), right, up — screen-space pan axes."""
        eye = self.eye()
        forward = _norm(_sub(self.target, eye))
        right = _norm(_cross(forward, (0.0, 1.0, 0.0)))
        if right[0] == 0.0 and right[1] == 0.0 and right[2] == 0.0:
            right = (1.0, 0.0, 0.0)
        up = _cross(right, forward)
        return forward, right, up

    def orbit(self, dx: float, dy: float) -> None:
        self.yaw += dx
        self.pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch + dy))

    def pan(self, dx: float, dy: float) -> None:
        """Screen-space pan; translation scales with orbit distance."""
        _forward, right, up = self.basis()
        scale = self.distance * 0.0022
        self.target[0] -= right[0] * dx * scale - up[0] * dy * scale
        self.target[1] -= right[1] * dx * scale - up[1] * dy * scale
        self.target[2] -= right[2] * dx * scale - up[2] * dy * scale

    def zoom(self, factor: float) -> None:
        zmin = max(ZOOM_MIN, float(getattr(self, "zoom_min", ZOOM_MIN)))
        zmax = max(zmin + 1.0, float(getattr(self, "zoom_max", ZOOM_MAX)))
        self.distance = max(zmin, min(zmax, self.distance * float(factor)))

    def zoom_toward(self, factor: float, point: Optional[Sequence[float]] = None) -> None:
        """Zoom, optionally sliding the pivot toward a world point (cursor / selection)."""
        self.zoom(factor)
        if point is None:
            return
        self.target = list(zoom_toward_target(self.target, point, factor))

    def frame(self, center, radius: float, *, keep_orientation: bool = False) -> None:
        self.target = [float(center[0]), float(center[1]), float(center[2])]
        r = max(2.5, float(radius))
        self.distance = fit_distance(r)
        self.zoom_min = ZOOM_MIN
        self.zoom_max = max(ZOOM_MAX, self.distance * 8.0, r * 24.0)
        if not keep_orientation:
            self.yaw = 0.7
            self.pitch = 0.4

    def frame_selection(self, center, radius: float = 2.5) -> None:
        """Orbit around a block without flipping yaw/pitch."""
        self.target = [float(center[0]), float(center[1]), float(center[2])]
        want = max(3.0, float(radius) * 2.8)
        if self.distance > want * 1.8 or self.distance < want * 0.45:
            self.distance = want

    def canvas_ndc(self, x: float, y: float, width: int, height: int) -> Tuple[float, float]:
        """
        Canvas pixels (origin top-left) to clip NDC matching the flip-Y blit.

        PhotoImage row 0 is glReadPixels' bottom row, so canvas top is NDC y = -1.
        """
        width = max(1, int(width))
        height = max(1, int(height))
        ndc_x = (2.0 * float(x) / width) - 1.0
        ndc_y = (2.0 * float(y) / height) - 1.0
        return ndc_x, ndc_y

    def screen_ray(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
        proj: Sequence[Sequence[float]],
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """World-space ray origin + direction for a canvas click."""
        import numpy as np

        ndc_x, ndc_y = self.canvas_ndc(x, y, width, height)
        view = np.asarray(self.view_matrix(), dtype=np.float64)
        projection = np.asarray(proj, dtype=np.float64)
        try:
            inv = np.linalg.inv(projection @ view)
        except np.linalg.LinAlgError:
            eye = self.eye()
            return eye, (0.0, 0.0, -1.0)
        near = inv @ np.array((ndc_x, ndc_y, -1.0, 1.0))
        far = inv @ np.array((ndc_x, ndc_y, 1.0, 1.0))
        if abs(float(near[3])) > 1e-8:
            near = near / near[3]
        if abs(float(far[3])) > 1e-8:
            far = far / far[3]
        origin = (float(near[0]), float(near[1]), float(near[2]))
        direction = (float(far[0] - near[0]), float(far[1] - near[1]), float(far[2] - near[2]))
        length = (direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2) ** 0.5
        if length < 1e-8:
            return origin, (0.0, 0.0, -1.0)
        return origin, (direction[0] / length, direction[1] / length, direction[2] / length)
