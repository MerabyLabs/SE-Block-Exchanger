"""Orbit camera and 4x4 helpers for the preview."""

from __future__ import annotations

import math
from typing import Sequence, Tuple


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


def perspective(fovy_deg: float, aspect: float, near: float, far: float) -> list:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    a = aspect if aspect > 1e-4 else 1.0
    return [
        [f / a, 0.0, 0.0, 0.0],
        [0.0, f, 0.0, 0.0],
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


class OrbitCamera:
    def __init__(self) -> None:
        self.target = [0.0, 0.0, 0.0]
        self.distance = 40.0
        self.yaw = 0.6
        self.pitch = 0.45

    def eye(self) -> Tuple[float, float, float]:
        cp = math.cos(self.pitch)
        x = self.target[0] + self.distance * cp * math.sin(self.yaw)
        y = self.target[1] + self.distance * math.sin(self.pitch)
        z = self.target[2] + self.distance * cp * math.cos(self.yaw)
        return (x, y, z)

    def view_matrix(self) -> list:
        return look_at(self.eye(), self.target, (0.0, 1.0, 0.0))

    def orbit(self, dx: float, dy: float) -> None:
        self.yaw += dx
        self.pitch = max(-1.2, min(1.2, self.pitch + dy))

    def pan(self, dx: float, dy: float) -> None:
        self.target[0] -= dx * self.distance * 0.002
        self.target[1] += dy * self.distance * 0.002

    def zoom(self, factor: float) -> None:
        self.distance = max(2.0, min(4000.0, self.distance * factor))

    def frame(self, center, radius: float) -> None:
        self.target = [float(center[0]), float(center[1]), float(center[2])]
        self.distance = max(6.0, float(radius) * 2.4)
        self.yaw = 0.7
        self.pitch = 0.4
