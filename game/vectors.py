"""Small, renderer-independent 3D geometry value objects."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec3:
    """A position or displacement in world units; y is always vertical."""

    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __truediv__(self, scalar: float) -> "Vec3":
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Vec3":
        length = self.length()
        if length == 0:
            return ZERO_VEC3
        return self / length

    def is_finite(self) -> bool:
        return math.isfinite(self.x) and math.isfinite(self.y) and math.isfinite(self.z)


ZERO_VEC3 = Vec3(0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Aabb:
    """Entity box measured from a feet-centred Transform position."""

    half_x: float
    height: float
    half_z: float

    def __post_init__(self) -> None:
        if self.half_x <= 0 or self.height <= 0 or self.half_z <= 0:
            raise ValueError("Aabb dimensions must be positive.")

    def bounds_at(self, feet_position: Vec3) -> tuple[float, float, float, float, float, float]:
        return (
            feet_position.x - self.half_x,
            feet_position.y,
            feet_position.z - self.half_z,
            feet_position.x + self.half_x,
            feet_position.y + self.height,
            feet_position.z + self.half_z,
        )
